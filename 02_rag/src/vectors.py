import numpy as np


def normalize_vectors(vectors: list[list[float]], count: int) -> np.ndarray:
    if not isinstance(vectors, list) or len(vectors) != count or not vectors:
        raise ValueError("Cantidad incorrecta de vectores.")
    if any(not isinstance(row, list) or not row
           or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in row) for row in vectors):
        raise ValueError("Los vectores deben contener números, sin valores booleanos.")
    matrix = np.array(vectors, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Dimensiones o valores no finitos en los vectores.")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("No se puede normalizar un vector nulo o con norma no finita.")
    return matrix / norms
