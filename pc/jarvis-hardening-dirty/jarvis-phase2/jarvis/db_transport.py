"""Direct PostgreSQL transport for the unprivileged web process.

The legacy CLI path remains for other workers.  In direct mode only the
fixed local ``docker exec ... psql`` calls are translated; no Docker socket is
opened and no SQL is accepted from an HTTP request by this module.
"""
from __future__ import annotations

import os
import re
import subprocess


_ROLE = re.compile(r"\bSET\s+SESSION\s+AUTHORIZATION\s+(ai_reader|human_approver)\s*;", re.I)
_OTHER_ROLE = re.compile(r"\bSET\s+SESSION\s+AUTHORIZATION\b", re.I)
_VARIABLE = re.compile(r":'([A-Za-z_][A-Za-z_0-9]*)'")


def _direct(command, *, input=None, timeout=None, **kwargs):
    import psycopg
    from psycopg import sql as pgsql

    if not kwargs.get("text", True):
        raise ValueError("direct PostgreSQL transport requires text output")
    args = list(command)
    if "-Atc" in args:
        statement = args[args.index("-Atc") + 1]
    elif "-c" in args:
        statement = args[args.index("-c") + 1]
    elif "-f" in args and args[args.index("-f") + 1] == "-":
        statement = input or ""
    else:
        raise ValueError("unsupported psql invocation")

    variables = {}
    for i, arg in enumerate(args[:-1]):
        if arg == "-v" and "=" in args[i + 1]:
            key, value = args[i + 1].split("=", 1)
            variables[key] = value
    sql_lines = []
    for line in statement.splitlines():
        meta = line.strip().lower()
        if meta in (r"\set on_error_stop on", r"\pset tuples_only on",
                    r"\pset format unaligned"):
            continue
        if meta.startswith("\\"):
            raise ValueError("unsupported psql meta command")
        sql_lines.append(line)
    statement = "\n".join(sql_lines)
    statement, role_count = _ROLE.subn(lambda m: "SET ROLE " + m[1].lower() + ";", statement)
    if _OTHER_ROLE.search(statement):
        raise ValueError("unsupported database role")
    # Queries with no explicit role run under the narrowly granted web login.
    password_file = os.environ["JARVIS_DB_PASSWORD_FILE"]
    with open(password_file, encoding="utf-8") as stream:
        password = stream.read().strip()
    if not password:
        raise ValueError("database password is empty")
    try:
        with psycopg.connect(host=os.environ.get("JARVIS_DB_HOST", "127.0.0.1"),
                             port=int(os.environ.get("JARVIS_DB_PORT", "5433")),
                             dbname="n8n", user="jarvis_web", password=password,
                             connect_timeout=min(int(timeout or 10), 10)) as conn:
            # psql's :'name' quoting is replaced with libpq's safe SQL literal
            # quoting; unknown variables fail closed rather than passing SQL.
            def quoted(match):
                name = match[1]
                if name not in variables:
                    raise ValueError("missing SQL variable: " + name)
                return pgsql.Literal(variables[name]).as_string(conn)
            statement = _VARIABLE.sub(quoted, statement)
            with conn.cursor() as cur:
                cur.execute(statement)
                lines = []
                while True:
                    if cur.description is not None:
                        for row in cur.fetchall():
                            if len(row) == 1:
                                value = row[0]
                                if isinstance(value, (dict, list)):
                                    import json
                                    value = json.dumps(value, ensure_ascii=False, default=str)
                                lines.append("" if value is None else str(value))
                            else:
                                lines.append("|".join("" if x is None else str(x) for x in row))
                    if not cur.nextset():
                        break
        return subprocess.CompletedProcess(command, 0, "\n".join(lines) + ("\n" if lines else ""), "")
    except (psycopg.Error, OSError, ValueError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def run(command, *args, **kwargs):
    """Run a local psql command directly in web mode; delegate all others."""
    if (os.environ.get("JARVIS_MEMORY_TRANSPORT") != "direct-pg"
            or not isinstance(command, (list, tuple))
            or len(command) < 4 or command[0] != "docker"
            or command[1] != "exec" or "psql" not in command):
        return subprocess.run(command, *args, **kwargs)
    if args:
        raise TypeError("positional subprocess.run arguments are unsupported")
    return _direct(command, **kwargs)
