import type { QueuedTimeOperation } from "./types";

const DATABASE = "benson-erp-field";
const STORE = "time-entry-operations";
let connection: Promise<IDBDatabase> | null = null;

function database() {
  if (connection) return connection;
  connection = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => {
        request.result.close();
        connection = null;
      };
      resolve(request.result);
    };
    request.onerror = () => {
      connection = null;
      reject(request.error);
    };
  });
  return connection;
}

export async function queueTimeOperation(operation: QueuedTimeOperation) {
  const db = await database();
  await transaction(db, "readwrite", (store) => store.put(operation));
}

export async function listTimeOperations(tenantId: string, userId: string) {
  const db = await database();
  const operations = await new Promise<QueuedTimeOperation[]>((resolve, reject) => {
    const request = db.transaction(STORE).objectStore(STORE).getAll();
    request.onsuccess = () => resolve(request.result as QueuedTimeOperation[]);
    request.onerror = () => reject(request.error);
  });
  return operations
    .filter((operation) => operation.tenant_id === tenantId && operation.user_id === userId)
    .sort((left, right) => left.created_at.localeCompare(right.created_at));
}

export async function removeTimeOperation(id: string) {
  const db = await database();
  await transaction(db, "readwrite", (store) => store.delete(id));
}

function transaction(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest,
) {
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
    action(tx.objectStore(STORE));
  });
}
