"""Start the weather display.  Same as:  python -m wxdisplay

Settings live in config.toml (copy config.example.toml to get started).
Run  python weather.py --help  for options.
"""

import sys

from wxdisplay.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
