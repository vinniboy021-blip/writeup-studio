"""Explicit local administration, without credentials in command arguments."""

import argparse
import getpass
import sys

from email_validator import validate_email
from sqlalchemy import select, update

from app.db import SessionLocal, utcnow
from app.models import SessionModel, User
from app.security import audit, password_hash


def main():
    parser = argparse.ArgumentParser(description="Administração local do CTF Writeup Studio")
    parser.add_argument("command", choices=["create-admin", "reset-password", "disable-user"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrador")
    parser.add_argument("--password-stdin", action="store_true", help="Ler senha de stdin para automação")
    args = parser.parse_args()
    email = validate_email(args.email, check_deliverability=False).normalized.lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.command == "create-admin" and user:
            parser.error("Usuário já existe; promoção deve ser feita por um administrador autenticado")
        if args.command != "create-admin" and user is None:
            parser.error("Usuário não encontrado")
        if args.command == "disable-user":
            user.is_active = False
        else:
            secret = (
                sys.stdin.readline().rstrip("\r\n")
                if args.password_stdin
                else getpass.getpass("Senha (mínimo 12 caracteres): ")
            )
            if not 12 <= len(secret) <= 128:
                parser.error("Senha deve ter de 12 a 128 caracteres")
            if args.command == "create-admin":
                user = User(
                    email=email, name=args.name, is_admin=True, is_active=True, password_hash=password_hash.hash(secret)
                )
                db.add(user)
                db.flush()
            else:
                user.password_hash = password_hash.hash(secret)
        db.execute(update(SessionModel).where(SessionModel.user_id == user.id).values(revoked_at=utcnow()))
        audit(db, user, "admin.cli." + args.command, "user", user.id, {"via": "local-cli"})
        db.commit()
    print("Operação concluída. Nenhuma senha foi registrada.")


if __name__ == "__main__":
    main()
