# This is an example jobs file, such a jobs file isn't necessary at all, but
# currently included for simplicity sake

injected_deps = ['mce-dev',
                 'libgles2-mesa-dev', # FIXME
                 'python3-gps', # pkg-gps weirdness
                 'xvfb',
                 ]

import sys
sys.path.insert(0, '../jenkins-integration')
from repos_core import _jobs

jobs = list(_jobs.keys())
