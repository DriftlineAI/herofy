// Temporary test component - delete after verifying Data Connect works
import { useGetCustomersPublic } from '@herofy/dataconnect/react';

// Test workspace ID - replace with real one from your seed data
const TEST_WORKSPACE_ID = '11111111-1111-1111-1111-111111111111';

export function DataConnectTest() {
  const { data, isLoading, error } = useGetCustomersPublic({
    workspaceId: TEST_WORKSPACE_ID
  });

  return (
    <div className="p-4 bg-charcoal-800 text-cream-100 rounded-lg m-4">
      <h2 className="text-lg font-bold mb-2">Data Connect Test</h2>

      {isLoading && <p>Loading customers...</p>}

      {error && (
        <p className="text-red-400">
          Error: {error.message}
        </p>
      )}

      {data && (
        <div>
          <p className="text-green-400 mb-2">
            ✓ Connected! Found {data.customers.length} customers
          </p>
          <ul className="text-sm">
            {data.customers.map(c => (
              <li key={c.id}>• {c.name} ({c.lifecycle})</li>
            ))}
          </ul>
        </div>
      )}

      {data?.customers.length === 0 && (
        <p className="text-yellow-400">
          No customers yet. The database is empty.
        </p>
      )}
    </div>
  );
}
