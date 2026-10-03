"""Proveedor Git: una interfaz pequeña y una implementación simulada en un archivo JSON.

La interfaz solo tiene lo que el procedimiento PR-TIC-004 permite hacer. No existe un
método para borrar repositorios, eliminar cuentas ni dar permisos: lo que el proveedor no
ofrece, el agente no lo puede ejecutar aunque el correo o el modelo lo pidan.

Cómo sería con un proveedor real (referencia; NO implementado en el curso, verificar en la
documentación oficial antes de usarlo y siempre con una cuenta de servicio de mínimo privilegio):

| Método                 | GitHub (organización)                                   | GitLab                                        |
|------------------------|---------------------------------------------------------|-----------------------------------------------|
| usuario / repos_de     | GET /users/{u}, GET /orgs/{org}/repos + /collaborators  | GET /users?username=, GET /projects/:id/members/all |
| transferir_propiedad   | PUT /repos/{o}/{r}/collaborators/{jefe} (permission=admin) o POST /repos/{o}/{r}/transfer | PUT/POST /projects/:id/members (access_level=50) |
| quitar_acceso          | DELETE /repos/{o}/{r}/collaborators/{u}                 | DELETE /projects/:id/members/:user_id         |
| revocar_tokens         | Enterprise/SSO: DELETE /orgs/{org}/credential-authorizations/{id} | DELETE /personal_access_tokens/:id (admin) |
| revocar_llaves_ssh     | GHES: DELETE /admin/keys/{id}                           | DELETE /users/:id/keys/:key_id (admin)        |
| bloquear_cuenta        | DELETE /orgs/{org}/members/{u}; GHES: PUT /users/{u}/suspended | POST /users/:id/block                   |

Una implementación real (GitHubProvider o GitLabProvider) cumpliría la misma interfaz y
leería su token de una variable de entorno; el grafo no cambia.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


class GitError(RuntimeError):
    pass


class GitProvider(Protocol):
    def usuario(self, login: str) -> dict | None: ...
    def repos_de(self, login: str) -> list[dict]: ...
    def transferir_propiedad(self, repo: str, de: str, a: str) -> str: ...
    def quitar_acceso(self, repo: str, login: str) -> str: ...
    def revocar_tokens(self, login: str) -> str: ...
    def revocar_llaves_ssh(self, login: str) -> str: ...
    def bloquear_cuenta(self, login: str) -> str: ...


class FakeGitProvider:
    """Proveedor simulado: el estado vive en un JSON local y cada cambio queda en auditoría."""

    def __init__(self, estado: Path, inicial: Path):
        self.path = Path(estado)
        self.inicial = Path(inicial)
        if not self.path.is_file():
            self.reiniciar()

    # -- persistencia -------------------------------------------------------------------
    def reiniciar(self) -> None:
        data = json.loads(self.inicial.read_text(encoding="utf-8"))
        data["auditoria"] = []
        self._guardar(data)

    def _leer(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _guardar(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _cambiar(self, accion: str, detalle: dict, cambio) -> str:
        data = self._leer()
        mensaje = cambio(data)
        data["auditoria"].append({"momento": datetime.now(timezone.utc).isoformat(), "accion": accion,
                                  **detalle, "resultado": mensaje})
        self._guardar(data)
        return mensaje

    def estado(self) -> dict:
        return copy.deepcopy(self._leer())

    # -- lectura -----------------------------------------------------------------------
    def usuario(self, login: str) -> dict | None:
        found = self._leer()["usuarios"].get(login)
        return copy.deepcopy(found) if found else None

    def repos_de(self, login: str) -> list[dict]:
        repos = []
        for nombre, repo in sorted(self._leer()["repositorios"].items()):
            if login in repo["miembros"]:
                owners = sorted(user for user, rol in repo["miembros"].items() if rol == "propietario")
                repos.append({"nombre": nombre, "rol": repo["miembros"][login], "propietarios": owners})
        return repos

    # -- escritura (solo lo que permite el procedimiento) ----------------------------------
    def _cuenta(self, data: dict, login: str) -> dict:
        if login not in data["usuarios"]:
            raise GitError(f"USUARIO_INEXISTENTE: {login}")
        return data["usuarios"][login]

    def _repo(self, data: dict, nombre: str) -> dict:
        if nombre not in data["repositorios"]:
            raise GitError(f"REPO_INEXISTENTE: {nombre}")
        return data["repositorios"][nombre]

    def transferir_propiedad(self, repo: str, de: str, a: str) -> str:
        def cambio(data):
            miembros = self._repo(data, repo)["miembros"]
            destino = self._cuenta(data, a)
            if miembros.get(de) != "propietario":
                raise GitError(f"NO_ES_PROPIETARIO: {de} en {repo}")
            if destino["estado"] != "activa":
                raise GitError(f"DESTINO_NO_ACTIVO: {a}")
            miembros[a] = "propietario"
            del miembros[de]
            return f"{repo}: propiedad de {de} a {a}"
        return self._cambiar("transferir_propiedad", {"repo": repo, "de": de, "a": a}, cambio)

    def quitar_acceso(self, repo: str, login: str) -> str:
        def cambio(data):
            miembros = self._repo(data, repo)["miembros"]
            if login not in miembros:
                return f"{repo}: {login} ya no tenía acceso"
            if miembros[login] == "propietario" and sum(r == "propietario" for r in miembros.values()) == 1:
                raise GitError(f"PROPIETARIO_UNICO: transferir {repo} antes de quitar el acceso")
            del miembros[login]
            return f"{repo}: acceso de {login} retirado"
        return self._cambiar("quitar_acceso", {"repo": repo, "usuario": login}, cambio)

    def revocar_tokens(self, login: str) -> str:
        def cambio(data):
            cuenta = self._cuenta(data, login)
            total, cuenta["tokens"] = len(cuenta["tokens"]), []
            return f"{login}: {total} tokens revocados"
        return self._cambiar("revocar_tokens", {"usuario": login}, cambio)

    def revocar_llaves_ssh(self, login: str) -> str:
        def cambio(data):
            cuenta = self._cuenta(data, login)
            total, cuenta["llaves_ssh"] = len(cuenta["llaves_ssh"]), []
            return f"{login}: {total} llaves SSH revocadas"
        return self._cambiar("revocar_llaves_ssh", {"usuario": login}, cambio)

    def bloquear_cuenta(self, login: str) -> str:
        def cambio(data):
            cuenta = self._cuenta(data, login)
            cuenta["estado"] = "bloqueada"
            return f"{login}: cuenta bloqueada"
        return self._cambiar("bloquear_cuenta", {"usuario": login}, cambio)


def verificar_baja(git, usuario: str, plan: dict) -> dict:
    """Lee el estado final del proveedor. Que un texto diga "cuenta bloqueada" no lo prueba."""
    cuenta = git.usuario(usuario) or {}
    repos = git.repos_de(usuario)
    problemas = []
    if cuenta.get("estado") != "bloqueada":
        problemas.append(f"la cuenta sigue {cuenta.get('estado', 'sin estado')}")
    if cuenta.get("tokens"):
        problemas.append(f"quedan {len(cuenta['tokens'])} tokens")
    if cuenta.get("llaves_ssh"):
        problemas.append(f"quedan {len(cuenta['llaves_ssh'])} llaves SSH")
    if repos:
        problemas.append("conserva acceso a " + ", ".join(repo["nombre"] for repo in repos))
    for item in plan.get("acciones", []):
        if item["accion"] == "transferir_propiedad":
            owners = next((r["propietarios"] for r in git.repos_de(item["a"]) if r["nombre"] == item["repo"]), [])
            if item["a"] not in owners:
                problemas.append(f"{item['repo']} no quedó a nombre de {item['a']}")
    return {"ok": not problemas, "problemas": problemas, "estado_cuenta": cuenta.get("estado"),
            "repos_con_acceso": [repo["nombre"] for repo in repos]}
