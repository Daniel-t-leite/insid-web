"""
Cliente leve DB-API 2.0 para Turso (libSQL) via HTTP Pipeline API v2.
Zero dependências nativas/C/Rust — utiliza apenas `requests` (já incluído com Streamlit).
Compatível com sqlite3 e pandas.read_sql(query, conn).
"""

import base64
import datetime
import sqlite3
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import requests


def _normalizar_url_turso(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]
    elif url.startswith("ws://"):
        url = "http://" + url[len("ws://"):]
    if not url.endswith("/v2/pipeline"):
        url = url + "/v2/pipeline"
    return url


def _encode_arg(val: Any) -> dict:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(val)).decode("ascii")}
    if isinstance(val, (datetime.datetime, datetime.date)):
        return {"type": "text", "value": val.isoformat()}
    # Suporte a escalares numpy/pandas (ex: np.int64, np.float64)
    if hasattr(val, "item"):
        try:
            return _encode_arg(val.item())
        except Exception:
            pass
    return {"type": "text", "value": str(val)}


def _decode_cell(cell: dict) -> Any:
    ctype = cell.get("type")
    if ctype == "null" or ctype is None:
        return None
    if ctype == "integer":
        return int(cell["value"])
    if ctype == "float":
        return float(cell["value"])
    if ctype == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")


def _raise_sqlite_error(message: str) -> None:
    lower = message.lower()
    if "unique constraint" in lower or "integrity" in lower or "foreign key" in lower or "not null constraint" in lower:
        raise sqlite3.IntegrityError(message)
    raise sqlite3.OperationalError(message)


class TursoCursor:
    def __init__(self, conn: "TursoConnection"):
        self._conn = conn
        self.description: Optional[Tuple[Tuple[Any, ...], ...]] = None
        self.rowcount: int = -1
        self.lastrowid: Optional[int] = None
        self._rows: List[Tuple[Any, ...]] = []
        self._index: int = 0

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> "TursoCursor":
        stmt: dict = {"sql": sql}
        if params:
            stmt["args"] = [_encode_arg(p) for p in params]

        result = self._conn._pipeline([{"type": "execute", "stmt": stmt}, {"type": "close"}])[0]
        self._apply_result(result)
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> "TursoCursor":
        reqs = []
        for params in seq_of_params:
            stmt: dict = {"sql": sql}
            if params:
                stmt["args"] = [_encode_arg(p) for p in params]
            reqs.append({"type": "execute", "stmt": stmt})

        if not reqs:
            self.rowcount = 0
            return self

        # Envia em lotes de 50 para evitar payloads HTTP excessivos
        total_affected = 0
        last_res = None
        batch_size = 50
        for i in range(0, len(reqs), batch_size):
            chunk = reqs[i:i + batch_size] + [{"type": "close"}]
            results = self._conn._pipeline(chunk)
            for res in results[:-1]:
                total_affected += int(res.get("affected_row_count") or 0)
                last_res = res

        if last_res is not None:
            self._apply_result(last_res)
        self.rowcount = total_affected
        return self

    def _apply_result(self, result: dict) -> None:
        cols = result.get("cols") or []
        if cols:
            self.description = tuple((c.get("name"), None, None, None, None, None, None) for c in cols)
        else:
            self.description = None

        raw_rows = result.get("rows") or []
        self._rows = [tuple(_decode_cell(cell) for cell in row) for row in raw_rows]
        self._index = 0
        self.rowcount = int(result.get("affected_row_count") or 0)
        lrid = result.get("last_insert_rowid")
        self.lastrowid = int(lrid) if lrid is not None else None

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchmany(self, size: int = 1) -> List[Tuple[Any, ...]]:
        end = self._index + size
        rows = self._rows[self._index:end]
        self._index = min(end, len(self._rows))
        return rows

    def fetchall(self) -> List[Tuple[Any, ...]]:
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def close(self) -> None:
        self._rows = []

    def __iter__(self):
        return iter(self.fetchall())


class TursoConnection:
    """Conexão compatível com sqlite3.Connection usando Turso HTTP API v2."""

    def __init__(self, url: str, auth_token: str, timeout: int = 20):
        self._endpoint = _normalizar_url_turso(url)
        self._headers = {
            "Authorization": f"Bearer {auth_token.strip()}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._session = requests.Session()

    def _pipeline(self, requests_list: List[dict]) -> List[dict]:
        try:
            resp = self._session.post(
                self._endpoint,
                headers=self._headers,
                json={"requests": requests_list},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise sqlite3.OperationalError(f"Erro de ligação ao Turso: {exc}") from exc

        if resp.status_code != 200:
            raise sqlite3.OperationalError(f"Turso HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        out = []
        for item in data.get("results", []):
            if item.get("type") == "error":
                msg = (item.get("error") or {}).get("message", "Erro desconhecido no Turso")
                _raise_sqlite_error(msg)
            response = item.get("response") or {}
            out.append(response.get("result") or {})
        return out

    def cursor(self) -> TursoCursor:
        return TursoCursor(self)

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> TursoCursor:
        cur = self.cursor()
        return cur.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> TursoCursor:
        cur = self.cursor()
        return cur.executemany(sql, seq_of_params)

    def commit(self) -> None:
        # Cada operação HTTP pipeline do Turso já é confirmada automaticamente
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def __enter__(self) -> "TursoConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
