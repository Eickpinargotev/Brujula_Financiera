"""Páginas HTML: login, logout y el dashboard protegido."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from brujula.config.settings import get_settings
from brujula.core.security import verify_password
from brujula.web import auth
from brujula.web.templating import templates

router = APIRouter(include_in_schema=False)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    if auth.is_authenticated(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, password: str = Form("")) -> Response:
    settings = get_settings()

    if not auth.login_allowed(request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Demasiados intentos. Espera unos minutos."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not verify_password(password, settings.dashboard_password):
        auth.register_failed_attempt(request)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Contraseña incorrecta."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    auth.reset_attempts(request)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    auth.set_session_cookie(response, settings)
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    auth.clear_session_cookie(response)
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> Response:
    if not auth.is_authenticated(request):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "dashboard.html", {})
