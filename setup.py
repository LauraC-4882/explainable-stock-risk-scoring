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
        "xgboost>=2.0",
        "arch>=6.3",
        "pandas-ta>=0.3.14b",
        "fastapi>=0.111",
        "uvicorn[standard]>=0.29",
        "pydantic>=2.7",
        "pydantic-settings>=2.2",
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
