"""Shared test plumbing. The scripts have no .py extension, so they are loaded
by path; nothing here touches the network or a real device."""
import importlib.machinery, importlib.util, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_script(rel, name=None):
    path = os.path.join(ROOT, rel)
    name = name or os.path.basename(rel).replace("-", "_")
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod
