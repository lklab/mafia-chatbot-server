import sys
import os

path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'messages')
if path not in sys.path :
    sys.path.append(path)
