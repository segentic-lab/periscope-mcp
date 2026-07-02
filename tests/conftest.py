import os
import sys
import tempfile

# Isolate the data root BEFORE anything imports config — tests must never
# touch the real projects/screenshots store.
os.environ.setdefault("PERISCOPE_DATA_DIR", tempfile.mkdtemp(prefix="periscope-test-data-"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
