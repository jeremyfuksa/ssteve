"""
SSTV Engine Core - Universal Python package setup
"""

from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="sstv-engine",
    version="1.0.0",
    description="Universal SSTV decoder/encoder engine for cross-platform applications",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="SSTV Decoder Team",
    license="MIT",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Communications :: Ham Radio",
    ],
    keywords="sstv ham-radio decoder encoder image audio",
    entry_points={
        "console_scripts": [
            "sstv-decode=sstv_engine.cli:decode_cli",
            "sstv-encode=sstv_engine.cli:encode_cli",
            "sstv-enhance=sstv_engine.cli:enhance_cli",
        ],
    },
)