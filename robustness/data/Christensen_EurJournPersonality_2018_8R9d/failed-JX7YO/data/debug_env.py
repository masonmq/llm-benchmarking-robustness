import sys, pkgutil, os
print('Python executable:', sys.executable)
print('Python version:', sys.version)
print('sys.path:', sys.path)
print('CWD:', os.getcwd())
print('List of top-level packages available:')
print(sorted([m.name for m in pkgutil.iter_modules()])[:50])
try:
    import numpy as np
    print('NumPy version:', np.__version__)
except Exception as e:
    print('Failed to import numpy:', repr(e))
try:
    import pandas as pd
    print('Pandas version:', pd.__version__)
except Exception as e:
    print('Failed to import pandas:', repr(e))
try:
    import scipy
    print('SciPy version:', scipy.__version__)
except Exception as e:
    print('Failed to import scipy:', repr(e))
try:
    import networkx as nx
    print('NetworkX version:', nx.__version__)
except Exception as e:
    print('Failed to import networkx:', repr(e))
try:
    import community
    print('python-louvain imported OK')
except Exception as e:
    print('Failed to import python-louvain:', repr(e))
