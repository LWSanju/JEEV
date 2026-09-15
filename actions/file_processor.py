"""Compatibility bridge: preserves the old file_processor tool name."""
from analyser import analyze_file

def file_processor(parameters=None,player=None,speak=None,**_):
    return analyze_file(parameters=parameters,player=player,speak=speak)
