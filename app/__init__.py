"""pcss-service: FastAPI application layer on top of the framework-free ``pcss`` core.

Layering (imports only point downwards):

    app.api        HTTP: routing, Pydantic validation, authentication dependency, error mapping
    app.services   business workflows (sharing / proofs / verification / recovery)
    app.security   password hashing, JWT, role + resource authorization policy
    app.storage    SQLAlchemy models and repository (SQLite in the demo)
    pcss           algorithms only (no FastAPI, HTTP, JWT, Tkinter or database)
"""
