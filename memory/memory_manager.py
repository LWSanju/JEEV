import json
import re
import sqlite3
import hashlib
from datetime import datetime
from threading import RLock
from pathlib import Path
import sys


# ============================================================
# PATHS
# ============================================================

def get_base_dir() -> Path:
    """
    Returns the project base directory.

    When running normally:
        C:\\Mark-XXXIX-OR-main\\

    When packaged/frozen:
        Uses the directory containing the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()

MEMORY_DIR = BASE_DIR / "memory"
MEMORY_PATH = MEMORY_DIR / "long_term.json"
DATABASE_PATH = MEMORY_DIR / "jeev_memory.db"

_lock = RLock()


# ============================================================
# MEMORY LIMITS
# ============================================================

# Personal memories are intentionally compact.
# Document memories are stored in SQLite and are not forced
# through the personal-memory limit.

MAX_VALUE_LENGTH = 1000
PROMPT_MEMORY_MAX_CHARS = 7000
DOCUMENT_CHUNK_SIZE = 3500
SEARCH_RESULT_MAX_CHARS = 12000


# ============================================================
# PERSONAL MEMORY
# ============================================================

def _empty_memory() -> dict:
    return {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }


def _ensure_database() -> None:
    """
    Creates the persistent document-memory database and tables
    if they do not already exist.
    """

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("PRAGMA foreign_keys=ON")

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT,
                file_type TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(document_id)
                    REFERENCES documents(id)
                    ON DELETE CASCADE,
                UNIQUE(document_id, chunk_index)
            )
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_document_name
            ON documents(file_name)
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunk_document
            ON document_chunks(document_id)
            """
        )

        db.commit()


# ============================================================
# PERSONAL MEMORY LOAD / SAVE
# ============================================================

def load_memory() -> dict:
    """
    Loads Jeev's personal memory from long_term.json.
    """

    if not MEMORY_PATH.exists():
        return _empty_memory()

    with _lock:
        try:
            data = json.loads(
                MEMORY_PATH.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                base = _empty_memory()

                for key in base:
                    if key not in data or not isinstance(data[key], dict):
                        data[key] = {}

                return data

        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")

    return _empty_memory()


def save_memory(memory: dict) -> None:
    """
    Saves personal memory to long_term.json.
    """

    if not isinstance(memory, dict):
        return

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    with _lock:
        try:
            MEMORY_PATH.write_text(
                json.dumps(
                    memory,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Memory] ⚠️ Save error: {e}")


# ============================================================
# PERSONAL MEMORY HELPERS
# ============================================================

def _truncate_value(val: str) -> str:
    text = str(val).strip()

    if len(text) > MAX_VALUE_LENGTH:
        return text[:MAX_VALUE_LENGTH].rstrip() + "…"

    return text


def _recursive_update(target: dict, updates: dict) -> bool:
    """
    Recursively merges extracted memory into existing memory.
    """

    changed = False

    if not isinstance(updates, dict):
        return False

    for key, value in updates.items():

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        # Nested category/object.
        if isinstance(value, dict) and "value" not in value:

            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True

            if _recursive_update(target[key], value):
                changed = True

            continue

        # Standard memory entry.
        if isinstance(value, dict) and "value" in value:
            new_val = _truncate_value(value["value"])
        else:
            new_val = _truncate_value(value)

        if not new_val:
            continue

        entry = {
            "value": new_val,
            "updated": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        existing = target.get(key, {})

        if (
            not isinstance(existing, dict)
            or existing.get("value") != new_val
        ):
            target[key] = entry
            changed = True

    return changed


def update_memory(memory_update: dict) -> dict:
    """
    Merges new personal memories into existing memory.
    """

    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    memory = load_memory()

    if _recursive_update(memory, memory_update):
        save_memory(memory)

        print(
            "[Memory] 💾 Saved personal memory: "
            f"{list(memory_update.keys())}"
        )

    return memory


def _all_personal_entries(memory: dict):
    """
    Iterates through all personal-memory entries.
    """

    if not isinstance(memory, dict):
        return

    for category, items in memory.items():

        if not isinstance(items, dict):
            continue

        for key, entry in items.items():

            if (
                isinstance(entry, dict)
                and entry.get("value")
            ):
                yield category, key, entry


# ============================================================
# PERSONAL MEMORY FORMATTING
# ============================================================

def _format_personal_memory(memory: dict) -> list[str]:
    lines = []

    identity = memory.get("identity", {})

    preferred = [
        "name",
        "age",
        "birthday",
        "city",
        "job",
        "language",
        "school",
        "nationality",
    ]

    # Important identity fields first.
    for field in preferred:

        entry = identity.get(field)

        if entry:
            value = (
                entry.get("value")
                if isinstance(entry, dict)
                else entry
            )

            if value:
                lines.append(
                    f"{field.title()}: {value}"
                )

    # Other identity fields.
    for key, entry in identity.items():

        if key in preferred:
            continue

        value = (
            entry.get("value")
            if isinstance(entry, dict)
            else entry
        )

        if value:
            lines.append(
                f"{key.replace('_', ' ').title()}: {value}"
            )

    sections = [
        ("Preferences", "preferences", 20),
        ("Active Projects / Goals", "projects", 20),
        ("People in their life", "relationships", 15),
        ("Wishes / Plans / Wants", "wishes", 15),
        ("Other notes", "notes", 15),
    ]

    for title, category, limit in sections:

        items = memory.get(category, {})

        if not items:
            continue

        lines.append("")
        lines.append(f"{title}:")

        ordered = sorted(
            items.items(),
            key=lambda pair: (
                str(pair[1].get("updated", ""))
                if isinstance(pair[1], dict)
                else ""
            ),
            reverse=True,
        )

        for key, entry in ordered[:limit]:

            value = (
                entry.get("value")
                if isinstance(entry, dict)
                else entry
            )

            if value:
                lines.append(
                    f"  - {key.replace('_', ' ').title()}: {value}"
                )

    return lines


# ============================================================
# DOCUMENT MEMORY
# ============================================================

def _hash_text(
    file_name: str,
    file_path: str,
    content: str,
) -> str:
    """
    Generates a stable SHA-256 hash for a document.

    Filename and path are included so two unrelated documents
    containing identical text do not silently become one memory.
    """

    raw = (
        f"{file_name}\n"
        f"{file_path}\n"
        f"{content}"
    ).encode(
        "utf-8",
        errors="replace",
    )

    return hashlib.sha256(raw).hexdigest()


def _make_chunks(
    content: str,
    size: int = DOCUMENT_CHUNK_SIZE,
) -> list[str]:
    """
    Splits document content into searchable chunks.
    """

    text = str(content or "").strip()

    if not text:
        return []

    chunks = []

    start = 0
    length = len(text)

    while start < length:

        end = min(
            start + size,
            length,
        )

        # Prefer splitting on a newline.
        if end < length:

            split = text.rfind(
                "\n",
                start,
                end,
            )

            if split > start + size // 2:
                end = split

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end

    return chunks


def save_document_memory(
    file_name: str,
    file_path: str,
    content: str,
    file_type: str = "document",
    summary: str = "",
) -> dict:
    """
    Persist knowledge returned by file/PDF analysis.

    The complete analysis is retained in SQLite while chunks
    make later retrieval possible without putting every old
    document into the Live prompt.
    """

    content = str(content or "").strip()

    if not content:
        return {
            "saved": False,
            "reason": "empty_content",
        }

    _ensure_database()

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    file_name = str(
        file_name or "Unknown file"
    ).strip()

    file_path = str(
        file_path or ""
    ).strip()

    file_type = str(
        file_type or "document"
    ).strip()

    summary = str(
        summary or ""
    ).strip()[:2000]

    file_hash = _hash_text(
        file_name,
        file_path,
        content,
    )

    chunks = _make_chunks(content)

    with _lock, sqlite3.connect(DATABASE_PATH) as db:

        db.execute("PRAGMA foreign_keys=ON")

        existing = db.execute(
            """
            SELECT id
            FROM documents
            WHERE file_hash = ?
            """,
            (file_hash,),
        ).fetchone()

        if existing:

            document_id = existing[0]

            db.execute(
                """
                UPDATE documents
                SET
                    file_name=?,
                    file_path=?,
                    file_type=?,
                    content=?,
                    summary=?,
                    updated=?
                WHERE id=?
                """,
                (
                    file_name,
                    file_path,
                    file_type,
                    content,
                    summary,
                    now,
                    document_id,
                ),
            )

            db.execute(
                """
                DELETE FROM document_chunks
                WHERE document_id=?
                """,
                (document_id,),
            )

            action = "updated"

        else:

            cursor = db.execute(
                """
                INSERT INTO documents
                (
                    file_hash,
                    file_name,
                    file_path,
                    file_type,
                    content,
                    summary,
                    created,
                    updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
                    file_name,
                    file_path,
                    file_type,
                    content,
                    summary,
                    now,
                    now,
                ),
            )

            document_id = cursor.lastrowid
            action = "saved"

        db.executemany(
            """
            INSERT INTO document_chunks
            (
                document_id,
                chunk_index,
                content
            )
            VALUES (?, ?, ?)
            """,
            [
                (
                    document_id,
                    index,
                    chunk,
                )
                for index, chunk in enumerate(chunks)
            ],
        )

        db.commit()

    print(
        f"[Memory] 📚 Document {action}: "
        f"{file_name} "
        f"({len(content):,} chars, "
        f"{len(chunks)} chunks)"
    )

    return {
        "saved": True,
        "action": action,
        "document_id": document_id,
        "file_name": file_name,
        "chunks": len(chunks),
    }


def list_document_memory(
    limit: int = 20,
) -> list[dict]:
    """
    Lists documents stored in persistent memory.
    """

    _ensure_database()

    limit = max(
        1,
        min(int(limit), 100),
    )

    with _lock, sqlite3.connect(DATABASE_PATH) as db:

        rows = db.execute(
            """
            SELECT
                id,
                file_name,
                file_path,
                file_type,
                summary,
                created,
                updated
            FROM documents
            ORDER BY updated DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": row[0],
            "file_name": row[1],
            "file_path": row[2],
            "file_type": row[3],
            "summary": row[4] or "",
            "created": row[5],
            "updated": row[6],
        }
        for row in rows
    ]


def search_document_memory(
    query: str,
    limit: int = 5,
) -> str:
    """
    Searches persistent document knowledge using words
    from the current query.
    """

    query = str(query or "").strip()

    if not query:
        return "No document-memory query was provided."

    _ensure_database()

    limit = max(
        1,
        min(int(limit), 10),
    )

    words = [
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9_@.+#-]+",
            query,
        )
        if len(word) >= 3
    ]

    words = list(
        dict.fromkeys(words)
    )[:12]

    with _lock, sqlite3.connect(DATABASE_PATH) as db:

        if not words:

            rows = db.execute(
                """
                SELECT
                    d.id,
                    d.file_name,
                    d.file_path,
                    d.file_type,
                    d.summary,
                    c.chunk_index,
                    c.content
                FROM document_chunks c
                JOIN documents d
                    ON d.id = c.document_id
                ORDER BY
                    d.updated DESC,
                    c.chunk_index ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        else:

            conditions = []
            params = []

            for word in words:

                like = f"%{word}%"

                conditions.append(
                    """
                    (
                        LOWER(c.content) LIKE ?
                        OR LOWER(d.file_name) LIKE ?
                        OR LOWER(d.summary) LIKE ?
                    )
                    """
                )

                params.extend(
                    [
                        like,
                        like,
                        like,
                    ]
                )

            sql = f"""
                SELECT
                    d.id,
                    d.file_name,
                    d.file_path,
                    d.file_type,
                    d.summary,
                    c.chunk_index,
                    c.content
                FROM document_chunks c
                JOIN documents d
                    ON d.id = c.document_id
                WHERE {" OR ".join(conditions)}
                ORDER BY
                    d.updated DESC,
                    c.chunk_index ASC
                LIMIT ?
            """

            params.append(limit * 2)

            rows = db.execute(
                sql,
                params,
            ).fetchall()

    if not rows:
        return (
            "No matching information was found "
            "in Jeev's persistent document memory."
        )

    blocks = []
    used = 0
    seen = set()

    for (
        doc_id,
        file_name,
        file_path,
        file_type,
        summary,
        chunk_index,
        content,
    ) in rows:

        key = (
            doc_id,
            chunk_index,
        )

        if key in seen:
            continue

        seen.add(key)

        block = (
            f"DOCUMENT: {file_name}\n"
            f"TYPE: {file_type}\n"
            f"PATH: {file_path}\n"
            f"CHUNK: {chunk_index + 1}\n"
        )

        if summary:
            block += (
                f"SUMMARY: {summary}\n"
            )

        block += (
            "CONTENT:\n"
            f"{content.strip()}"
        )

        if (
            used + len(block)
            > SEARCH_RESULT_MAX_CHARS
        ):

            remaining = (
                SEARCH_RESULT_MAX_CHARS
                - used
            )

            if remaining > 200:
                blocks.append(
                    block[:remaining] + "…"
                )

            break

        blocks.append(block)
        used += len(block)

    return "\n\n---\n\n".join(blocks)


def get_document_memory_context(
    limit: int = 10,
) -> str:
    """
    Creates a compact document-memory index for Jeev's prompt.
    """

    docs = list_document_memory(limit)

    if not docs:
        return ""

    lines = [
        "[PERSISTENT DOCUMENT MEMORY INDEX]",
        (
            "Jeev has permanently stored knowledge "
            "from these documents."
        ),
        (
            "Use the search_memory tool when a "
            "question depends on their contents."
        ),
    ]

    for doc in docs:

        summary = (
            doc["summary"]
            .replace("\n", " ")
            .strip()
        )

        if len(summary) > 220:
            summary = summary[:217] + "…"

        if summary:
            lines.append(
                f"- {doc['file_name']}: {summary}"
            )
        else:
            lines.append(
                f"- {doc['file_name']}"
            )

    return "\n".join(lines)


# ============================================================
# UNIFIED MEMORY SEARCH
# ============================================================

def search_memory(
    query: str,
    limit: int = 5,
) -> str:
    """
    Searches both personal memory and persistent
    document memory.
    """

    query = str(query or "").strip()

    personal = load_memory()

    personal_hits = []

    query_words = set(
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9_@.+#-]+",
            query,
        )
        if len(word) >= 3
    )

    for (
        category,
        key,
        entry,
    ) in _all_personal_entries(personal):

        value = str(
            entry.get("value", "")
        )

        haystack = (
            f"{category} "
            f"{key} "
            f"{value}"
        ).lower()

        if (
            not query_words
            or any(
                word in haystack
                for word in query_words
            )
        ):
            personal_hits.append(
                "PERSONAL MEMORY — "
                f"{category}/{key}: {value}"
            )

    document_result = search_document_memory(
        query,
        limit=limit,
    )

    parts = []

    if personal_hits:
        parts.append(
            "\n".join(
                personal_hits[:20]
            )
        )

    if (
        document_result
        and not document_result.startswith(
            "No matching"
        )
    ):
        parts.append(
            document_result
        )

    if not parts:
        return (
            "No matching persistent memory "
            "was found."
        )

    return (
        "[JEEV PERSISTENT MEMORY SEARCH]\n\n"
        + "\n\n---\n\n".join(parts)
    )


# ============================================================
# PROMPT MEMORY
# ============================================================

def format_memory_for_prompt(
    memory: dict | None,
) -> str:
    """
    Formats personal and document memory for
    inclusion in Jeev's AI prompt.
    """

    if memory is None:
        memory = load_memory()

    lines = _format_personal_memory(
        memory
    )

    document_index = (
        get_document_memory_context(
            limit=10
        )
    )

    blocks = []

    if lines:
        blocks.append(
            "[WHAT YOU KNOW ABOUT THIS PERSON — "
            "use naturally, never recite like a list]\n"
            + "\n".join(lines)
        )

    if document_index:
        blocks.append(
            document_index
        )

    if not blocks:
        return ""

    result = "\n\n".join(blocks)

    if len(result) > PROMPT_MEMORY_MAX_CHARS:
        result = (
            result[
                :PROMPT_MEMORY_MAX_CHARS - 3
            ]
            + "…"
        )

    return result + "\n"


# ============================================================
# LLM PERSONAL MEMORY EXTRACTION
# ============================================================

def should_extract_memory(
    user_text: str,
    jarvis_text: str,
    api_key: str = "",
) -> bool:
    """
    Uses Jeev's configured OpenRouter client to determine
    whether a conversation contains durable information.
    """

    try:
        from or_client import client

        combined = (
            f"User: {str(user_text)[:1000]}\n"
            f"Jeev: {str(jarvis_text)[:1500]}"
        )

        result = client.chat(
            (
                "Does this conversation contain ANY "
                "durable information worth remembering?\n"
                "Include personal facts, preferences, "
                "active projects, goals, relationships, "
                "future plans, recurring habits, or "
                "important decisions about the user's work.\n"
                "Do not save one-time commands, temporary "
                "weather, search results, or casual filler.\n"
                "Reply only YES or NO.\n\n"
                + combined
            ),
            system=(
                "You are a memory relevance checker. "
                "Reply only YES or NO."
            ),
            max_tokens=5,
            temperature=0.0,
        )

        return "YES" in str(result).upper()

    except Exception as e:

        print(
            f"[Memory] ⚠️ Stage1 check failed: {e}"
        )

        return False


def extract_memory(
    user_text: str,
    jarvis_text: str,
    api_key: str = "",
) -> dict:
    """
    Extracts durable personal/project information
    using the configured OpenRouter client.
    """

    try:
        from or_client import client

        combined = (
            f"User: {str(user_text)[:1800]}\n"
            f"Jeev: {str(jarvis_text)[:1800]}"
        )

        raw = client.chat(
            (
                "Extract ALL durable personal/project "
                "facts from this conversation.\n"
                "Return ONLY valid JSON. Use {} if "
                "nothing is worth saving.\n\n"

                "Categories:\n"

                "identity: name, age, birthday, city, "
                "country, job, school, language\n"

                "preferences: favorites, likes, "
                "dislikes, hobbies, interests\n"

                "projects: projects, technical work, "
                "active goals, architecture decisions\n"

                "relationships: important people\n"

                "wishes: future plans, things to buy, "
                "travel plans\n"

                "notes: other durable facts, recurring "
                "habits, important decisions\n\n"

                "Be liberal but do not invent information. "
                "Keep values concise.\n"

                "Use "
                "{\"category\":{\"key\":{\"value\":\"fact\"}}} "
                "format.\n\n"

                f"Conversation:\n{combined}\n\n"
                "JSON:"
            ),
            system=(
                "Return ONLY valid JSON. "
                "No markdown or explanation."
            ),
            max_tokens=1600,
            temperature=0.2,
        )

        clean = str(
            raw or ""
        ).strip()

        # Remove accidental markdown fences.
        clean = re.sub(
            r"^```(?:json)?",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()

        clean = re.sub(
            r"```$",
            "",
            clean,
        ).strip()

        if (
            not clean
            or clean == "{}"
        ):
            return {}

        data = json.loads(clean)

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except json.JSONDecodeError:
        return {}

    except Exception as e:

        # Do not spam the console for normal rate-limit
        # failures.
        if "429" not in str(e):

            print(
                f"[Memory] ⚠️ Extract failed: {e}"
            )

        return {}


# ============================================================
# DIRECT MEMORY COMMANDS
# ============================================================

def remember(
    key: str,
    value: str,
    category: str = "notes",
) -> str:
    """
    Directly stores a memory.
    """

    valid = {
        "identity",
        "preferences",
        "projects",
        "relationships",
        "wishes",
        "notes",
    }

    if category not in valid:
        category = "notes"

    update_memory(
        {
            category: {
                key: {
                    "value": value
                }
            }
        }
    )

    return (
        f"Remembered: "
        f"{category}/{key} = {value}"
    )


def forget(
    key: str,
    category: str = "notes",
) -> str:
    """
    Removes a specific personal memory.
    """

    valid = {
        "identity",
        "preferences",
        "projects",
        "relationships",
        "wishes",
        "notes",
    }

    if category not in valid:
        category = "notes"

    memory = load_memory()

    cat = memory.get(
        category,
        {},
    )

    if key in cat:

        del cat[key]

        memory[category] = cat

        save_memory(memory)

        return (
            f"Forgotten: "
            f"{category}/{key}"
        )

    return (
        f"Not found: "
        f"{category}/{key}"
    )


# Backward-compatible alias.
forget_memory = forget


# ============================================================
# INITIALIZE DATABASE
# ============================================================

try:
    _ensure_database()

except Exception as e:

    print(
        "[Memory] ⚠️ Database initialization "
        f"failed: {e}"
    )