// Herofy Database Client
// PostgreSQL connection pool for use across the monorepo

import pg from 'pg';

const { Pool } = pg;

let pool: pg.Pool | null = null;

/**
 * Get or create the database connection pool
 */
export function getPool(connectionString?: string): pg.Pool {
  if (!pool) {
    const connString = connectionString || process.env.DATABASE_URL;

    if (!connString) {
      throw new Error('DATABASE_URL environment variable is not set');
    }

    pool = new Pool({
      connectionString: connString,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });

    // Handle pool errors
    pool.on('error', (err) => {
      console.error('Unexpected error on idle database client:', err);
    });
  }

  return pool;
}

/**
 * Execute a parameterized SQL query
 */
export async function query<T = unknown>(
  sql: string,
  params: unknown[] = []
): Promise<pg.QueryResult<T>> {
  const client = getPool();
  return client.query<T>(sql, params);
}

/**
 * Execute a transaction with automatic rollback on error
 */
export async function transaction<T>(
  fn: (client: pg.PoolClient) => Promise<T>
): Promise<T> {
  const client = await getPool().connect();

  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Close the connection pool (for graceful shutdown)
 */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

/**
 * Helper to get a single row or null
 */
export async function queryOne<T = unknown>(
  sql: string,
  params: unknown[] = []
): Promise<T | null> {
  const result = await query<T>(sql, params);
  return result.rows[0] || null;
}

/**
 * Helper to get all rows
 */
export async function queryAll<T = unknown>(
  sql: string,
  params: unknown[] = []
): Promise<T[]> {
  const result = await query<T>(sql, params);
  return result.rows;
}

/**
 * Helper for INSERT ... RETURNING *
 */
export async function insert<T = unknown>(
  table: string,
  data: Record<string, unknown>
): Promise<T> {
  const keys = Object.keys(data);
  const values = Object.values(data);
  const placeholders = keys.map((_, i) => `$${i + 1}`).join(', ');
  const columns = keys.join(', ');

  const sql = `INSERT INTO ${table} (${columns}) VALUES (${placeholders}) RETURNING *`;
  const result = await query<T>(sql, values);

  return result.rows[0];
}

/**
 * Helper for UPDATE ... RETURNING *
 */
export async function update<T = unknown>(
  table: string,
  id: string,
  data: Record<string, unknown>
): Promise<T | null> {
  const keys = Object.keys(data);
  const values = Object.values(data);

  if (keys.length === 0) {
    return queryOne<T>(`SELECT * FROM ${table} WHERE id = $1`, [id]);
  }

  const setClause = keys.map((k, i) => `${k} = $${i + 1}`).join(', ');
  const sql = `UPDATE ${table} SET ${setClause} WHERE id = $${keys.length + 1} RETURNING *`;

  const result = await query<T>(sql, [...values, id]);
  return result.rows[0] || null;
}

/**
 * Helper for DELETE
 */
export async function remove(table: string, id: string): Promise<boolean> {
  const result = await query(`DELETE FROM ${table} WHERE id = $1`, [id]);
  return (result.rowCount ?? 0) > 0;
}
