from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings

oauth = OAuth()


def register_google(oauth: OAuth) -> None:
    settings = get_settings()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
        redirect_uri=settings.google_redirect_uri,
    )
