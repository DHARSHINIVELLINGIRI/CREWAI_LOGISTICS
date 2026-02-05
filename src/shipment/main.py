#!/usr/bin/env python
import sys
import warnings
from shipment.crew import EshipzOrchestrator

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

def run():
    """
    Run the crew.
    """
    import os
    inputs = {
        'weight': '2.5',
        'destination': 'Bangalore, India',
        'priority': 'High'
    }
    EshipzOrchestrator().crew().kickoff(inputs=inputs)

if __name__ == "__main__":
    run()