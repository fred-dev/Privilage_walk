#!/usr/bin/env python3
"""Run the test suite: python run_tests.py"""
import sys

import pytest

if __name__ == '__main__':
    sys.exit(pytest.main(['-q', 'test_app.py'] + sys.argv[1:]))
