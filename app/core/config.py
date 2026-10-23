from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_api_base: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    database_url: str = "sqlite:///./agentpay.db"
    llm_api_key: str = ""
    llm_model: str = ""
    app_env: str = "development"


settings = Settings()
