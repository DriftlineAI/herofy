"""
HITL Answer Service

Manages storage and retrieval of human-in-the-loop answers for paused agent runs.

Example:
    from services.hitl_answers import HITLAnswerService

    service = HITLAnswerService(db, workspace_id)

    # Save answers
    await service.save_answers(run_id, [
        {"question_id": "q1", "answer": "Yes"},
        {"question_id": "q2", "answer": "30 days"},
    ], user_id)

    # Get answers
    answers = await service.get_answers_dict(run_id)
    # {"q1": "Yes", "q2": "30 days"}
"""

from typing import Any

from core.logging import get_logger

logger = get_logger("HITLAnswerService")


class HITLAnswerService:
    """
    Service for managing HITL (Human-in-the-Loop) answers.

    Provides methods for storing and retrieving answers to
    clarifying questions from paused agent runs.
    """

    def __init__(self, db, workspace_id: str):
        """
        Initialize the service.

        Args:
            db: DatabaseClient instance
            workspace_id: Workspace UUID for scoping
        """
        self.db = db
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

        Args:
            agent_run_id: Agent run UUID
            question_id: Question identifier (matches clarifying_questions JSON)
            answer_text: User's answer text
            answered_by_user_id: User who answered (optional)

        Returns:
            Inserted agent_run_answer record
        """
        record = await self.db.insert(
            "agent_run_answers",
            {
                "workspace_id": self.workspace_id,
                "agent_run_id": agent_run_id,
                "question_id": question_id,
                "answer_text": answer_text,
                "answered_by_user_id": answered_by_user_id,
            },
        )

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
            List of inserted records
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
                # Handle duplicate key error gracefully (update instead)
                if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    await self.update_answer(
                        agent_run_id=agent_run_id,
                        question_id=question_id,
                        answer_text=str(answer_text),
                        answered_by_user_id=answered_by_user_id,
                    )
                else:
                    raise

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

        Args:
            agent_run_id: Agent run UUID
            question_id: Question identifier
            answer_text: New answer text
            answered_by_user_id: User who updated (optional)

        Returns:
            Updated record or None if not found
        """
        result = await self.db.query_one(
            """
            UPDATE agent_run_answers
            SET answer_text = $1,
                answered_by_user_id = COALESCE($2, answered_by_user_id),
                answered_at = NOW()
            WHERE agent_run_id = $3 AND question_id = $4
            RETURNING *
            """,
            [answer_text, answered_by_user_id, agent_run_id, question_id],
        )

        if result:
            logger.info(
                "hitl_answer_updated",
                agent_run_id=agent_run_id,
                question_id=question_id,
            )

        return result

    async def get_answers(self, agent_run_id: str) -> list[dict[str, Any]]:
        """
        Get all answers for an agent run.

        Args:
            agent_run_id: Agent run UUID

        Returns:
            List of answer records
        """
        return await self.db.query(
            """
            SELECT *
            FROM agent_run_answers
            WHERE agent_run_id = $1
            ORDER BY answered_at ASC
            """,
            [agent_run_id],
        )

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
            answer["question_id"]: answer["answer_text"]
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
        result = await self.db.execute(
            """
            DELETE FROM agent_run_answers
            WHERE agent_run_id = $1
            """,
            [agent_run_id],
        )

        # Parse "DELETE N" to get count
        deleted_count = 0
        if result and result.startswith("DELETE"):
            try:
                deleted_count = int(result.split()[-1])
            except (ValueError, IndexError):
                pass

        if deleted_count > 0:
            logger.info(
                "hitl_answers_deleted",
                agent_run_id=agent_run_id,
                count=deleted_count,
            )

        return deleted_count


# Convenience function for extracting answers
async def extract_answers_from_run(
    db,
    agent_run_id: str,
    workspace_id: str | None = None,
) -> dict[str, str]:
    """
    Extract answers from an agent run as a dictionary.

    Convenience function that doesn't require service instantiation.

    Args:
        db: DatabaseClient instance
        agent_run_id: Agent run UUID
        workspace_id: Optional workspace ID (for scoping)

    Returns:
        Dict mapping question_id to answer_text
    """
    if workspace_id:
        service = HITLAnswerService(db, workspace_id)
        return await service.get_answers_dict(agent_run_id)

    # Without workspace_id, query directly
    answers = await db.query(
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
