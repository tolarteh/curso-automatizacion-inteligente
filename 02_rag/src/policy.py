from chunking import Chunk
from settings import ROLES


def permitted(chunk: Chunk, role: str, *, remote: bool = False) -> bool:
    if role not in ROLES:
        raise ValueError(f"Rol desconocido: {role}")
    return (chunk.classification in ROLES[role] and not chunk.quarantined
            and not (remote and chunk.classification == "reservada"))


def validate_k(k: int) -> None:
    if type(k) is not int or not 1 <= k <= 20:
        raise ValueError("k debe ser un entero entre 1 y 20.")
