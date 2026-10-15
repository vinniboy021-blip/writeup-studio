# SPDX-License-Identifier: MIT
from fastapi import HTTPException

from app.security import authorize, authorize_team


def compatible_scope(db, actor, document, evidence):
    """A document must not give collaborators access to a narrower evidence scope."""
    authorize(db, actor, evidence, "read")
    if document.visibility == "team":
        if evidence.visibility != "team" or evidence.team_id != document.team_id:
            raise HTTPException(422, "Writeup de equipe exige evidência compartilhada com a mesma equipe")
    elif evidence.owner_id != document.owner_id and not actor.is_admin:
        raise HTTPException(422, "Evidência privada deve pertencer ao autor do writeup")


def validate_team(db, actor, team_id, visibility):
    if visibility == "team" and not team_id:
        raise HTTPException(422, "Visibilidade de equipe exige team_id")
    if team_id:
        authorize_team(db, actor, team_id, "write")
