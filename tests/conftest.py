import os, tempfile
# All test modules must select an isolated database before importing application modules.
os.environ['HEALTH_DATA']=tempfile.mkdtemp(prefix='health-test-')
