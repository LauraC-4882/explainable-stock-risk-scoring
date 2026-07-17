from setuptools import setup, find_packages

setup(
    name="stock_risk",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "yfinance>=0.2.40",
        "pandas>=2.0",
        "numpy>=1.26",
        "scikit-learn>=1.4",
        "xgboost>=2.0,<3.0",  # shap 0.49.1 can't parse XGBoost 3.x's base_score serialization format
        "shap==0.49.1",  # pinned exactly, not just >=0.45 — see CLAUDE.md for why
        "arch>=6.3",
        "ta>=0.11.0",
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
        "streamlit>=1.35",
        "plotly>=5.22",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.23",
            "httpx>=0.27",
            "black>=24.0",
            "ruff>=0.4",
            "mypy>=1.10",
        ]
    },
)
