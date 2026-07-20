from setuptools import setup, find_packages

setup(
    name="stock_risk",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "yfinance>=0.2.40",  # kept: options chain/news + index symbols + US fallback w/o a Twelve Data key
        "akshare>=1.18",  # CN A-shares + HK equities — verified live over eastmoney's Yahoo-style throttle
        "pandas>=2.0",
        "numpy>=1.26",
        "scikit-learn>=1.7,<1.8",  # committed model artefact is a 1.7.x pickle — 1.9.0 broke it in CI
        "xgboost>=2.0,<3.0",  # shap 0.49.1 can't parse XGBoost 3.x's base_score serialization format
        "shap==0.49.1",  # pinned exactly, not just >=0.45 — see CLAUDE.md for why
        "arch>=6.3",
        "ta>=0.11.0",
        "pandera[pandas]>=0.20",
        "fastapi>=0.111",
        "uvicorn[standard]>=0.29",
        "pydantic>=2.7",
        "pydantic-settings>=2.2",
        "email-validator>=2.0",
        "sqlmodel>=0.0.16",
        "pyjwt>=2.8",
        "bcrypt>=4.0",
        "prometheus-client>=0.20",
        "scipy>=1.13",
        "joblib>=1.4",
        "PyYAML>=6.0",
        "python-dotenv>=1.0",
        "loguru>=0.7",
        "cachetools>=5.3",  # TTL cache for MarketDataFetcher — see [C3]
        "gradio>=5.0",  # ui/gradio_app.py — [F3]'s Hugging Face Space
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.23",
            "httpx>=0.27",
            "black>=24.0",
            "ruff>=0.4",
            "mypy>=1.10",
            "playwright>=1.40",  # scripts/ui_shot.sh's screenshot harness
        ]
    },
)
