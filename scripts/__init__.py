"""CertPassly exam pipeline package (installed as certpassly_pipeline).

Scripts use flat imports (import paths). Adding this directory to sys.path
keeps that working after `pip install .` or `pip install -e .`.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
__version__ = '1.0.0'
