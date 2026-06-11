"""
HITL Answer Service (DataConnect Version)
Manages storage and retrieval of human-in-the-loop answers for paused agent runs using Firebase Data Connect
"""

from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("HITLAnswerServiceDC")


class HITLAnswerServiceDC:
    """
    Service for managing HITL (Human-in-the-Loop) answers using DataConnect.

    Provides methods for storing and retrieving answers to
    clarifying questions from paused agent runs.
    """

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        """
        Initialize the service.

        Args:
            dc: DataConnectClient instance
            workspace_id: Workspace UUID for scoping
        """
        self.dc = dc
        self.workspace_id = workspace_id

    async def save_answer(
        self,
        agent_run_id: str,
        question_id: str,
        answer_text: str,
        answered_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Save a single answer to an agent's clarifying question.

        Uses upsert - will update if answer already exists for this question.

        Args:
            agent_run_id: Agent run UUID
            question_id: Question identifier (matches clarifying_questions JSON)
            answer_text: User's answer text
            answered_by_user_id: User who answered (optional)

        Returns:
            Upserted agent_run_answer record
        """
        result = await self.dc.execute_mutation(
            "SaveAgentRunAnswer",
            {
                "workspaceId": self.workspace_id,
                "agentRunId": agent_run_id,
                "questionId": question_id,
                "answerText": answer_text,
                "answeredByUserId": answered_by_user_id,
            },
        )

        record = result.get("agentRunAnswer_upsert", {})

        logger.info(
            "hitl_answer_saved",
            agent_run_id=agent_run_id,
            question_id=question_id,
            answered_by=answered_by_user_id,
        )

        return record

    async def save_answers(
        self,
        agent_run_id: str,
        answers: list[dict[str, str]],
        answered_by_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Save multiple answers at once.

        Args:
            agent_run_id: Agent run UUID
            answers: List of {"question_id": "...", "answer": "..."} dicts
            answered_by_user_id: User who answered (optional)

        Returns:
            List of upserted records
        """
        results = []

        for answer in answers:
            question_id = answer.get("question_id") or answer.get("field")
            answer_text = answer.get("answer") or answer.get("answer_text", "")

            if not question_id:
                logger.warning(
                    "hitl_answer_missing_question_id",
                    agent_run_id=agent_run_id,
                    answer=answer,
                )
                continue

            try:
                record = await self.save_answer(
                    agent_run_id=agent_run_id,
                    question_id=question_id,
                    answer_text=str(answer_text),
                    answered_by_user_id=answered_by_user_id,
                )
                results.append(record)
            except Exception as e:
                logger.error(
                    "hitl_answer_save_failed",
                    agent_run_id=agent_run_id,
                    question_id=question_id,
                    error=str(e),
                )
                # Continue with other answers even if one fails
                continue

        logger.info(
            "hitl_answers_batch_saved",
            agent_run_id=agent_run_id,
            count=len(results),
        )

        return results

    async def update_answer(
        self,
        agent_run_id: str,
        question_id: str,
        answer_text: str,
        answered_by_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Update an existing answer.

        Since save_answer uses upsert, this is just an alias for consistency.

        Args:
            agent_run_id: Agent run UUID
            question_id: Question identifier
            answer_text: New answer text
            answered_by_user_id: User who updated (optional)

        Returns:
            Updated record
        """
        return await self.save_answer(
            agent_run_id=agent_run_id,
            question_id=question_id,
            answer_text=answer_text,
            answered_by_user_id=answered_by_user_id,
        )

    async def get_answers(self, agent_run_id: str) -> list[dict[str, Any]]:
        """
        Get all answers for an agent run.

        Args:
            agent_run_id: Agent run UUID

        Returns:
            List of answer records
        """
        result = await self.dc.execute_query(
            "GetAgentRunAnswers",
            {"agentRunId": agent_run_id},
        )

        answers = result.get("agentRunAnswers", [])

        # Transform nested answeredByUser to match legacy format
        for answer in answers:
            user = answer.pop("answeredByUser", None)
            if user:
                answer["answered_by_user_id"] = user.get("id")
                answer["answered_by_user_name"] = user.get("displayName")

        return answers

    async def get_answers_dict(self, agent_run_id: str) -> dict[str, str]:
        """
        Get answers as a dictionary: {question_id: answer_text}.

        This format is useful for merging into deal data during resume.

        Args:
            agent_run_id: Agent run UUID

        Returns:
            Dict mapping question_id to answer_text
        """
        answers = await self.get_answers(agent_run_id)
        return {
            answer["questionId"]: answer["answerText"]
            for answer in answers
        }

    async def has_all_answers(
        self,
        agent_run_id: str,
        required_question_ids: list[str],
    ) -> bool:
        """
        Check if all required questions have been answered.

        Args:
            agent_run_id: Agent run UUID
            required_question_ids: List of question IDs that need answers

        Returns:
            True if all required questions have answers
        """
        answers_dict = await self.get_answers_dict(agent_run_id)

        for question_id in required_question_ids:
            if question_id not in answers_dict:
                return False

        return True

    async def delete_answers(self, agent_run_id: str) -> int:
        """
        Delete all answers for an agent run.

        Typically called when an agent run is cancelled or restarted.

        Args:
            agent_run_id: Agent run UUID

        Returns:
            Number of deleted records
        """
        result = await self.dc.execute_mutation(
            "DeleteAgentRunAnswers",
            {"agentRunId": agent_run_id},
        )

        # DataConnect returns deleteMany result - extract count if available
        deleted_data = result.get("agentRunAnswer_deleteMany", {})
        deleted_count = deleted_data.get("count", 0) if isinstance(deleted_data, dict) else 0

        if deleted_count > 0:
            logger.info(
                "hitl_answers_deleted",
                agent_run_id=agent_run_id,
                count=deleted_count,
            )

        return deleted_count


# Convenience function for extracting answers
async def extract_answers_from_run(
    dc_or_db,
    agent_run_id: str,
    workspace_id: str | None = None,
) -> dict[str, str]:
    """
    Extract answers from an agent run as a dictionary.

    Convenience function that doesn't require service instantiation.
    Works with both DataConnect and DatabaseClient for backwards compatibility.

    Args:
        dc_or_db: DataConnectClient or DatabaseClient instance
        agent_run_id: Agent run UUID
        workspace_id: Optional workspace ID (for scoping)

    Returns:
        Dict mapping question_id to answer_text
    """
    from db.dataconnect_client import DataConnectClient

    # Check if using DataConnect
    if isinstance(dc_or_db, DataConnectClient):
        if workspace_id:
            service = HITLAnswerServiceDC(dc_or_db, workspace_id)
            return await service.get_answers_dict(agent_run_id)

        # Without workspace_id, query directly
        result = await dc_or_db.execute_query(
            "GetAgentRunAnswers",
            {"agentRunId": agent_run_id},
        )
        answers = result.get("agentRunAnswers", [])
        return {
            answer["questionId"]: answer["answerText"]
            for answer in answers
        }
    else:
        # Legacy DatabaseClient path
        if workspace_id:
            from services.hitl_answers import HITLAnswerService
            service = HITLAnswerService(dc_or_db, workspace_id)
            return await service.get_answers_dict(agent_run_id)

        # Without workspace_id, query directly
        answers = await dc_or_db.query(
            """
            SELECT question_id, answer_text
            FROM agent_run_answers
            WHERE agent_run_id = $1
            ORDER BY answered_at ASC
            """,
            [agent_run_id],
        )

        return {
            answer["question_id"]: answer["answer_text"]
            for answer in answers
        }
