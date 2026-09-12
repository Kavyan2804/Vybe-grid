import math
import random
from typing import List

def generate_synthetic_load(is_weekend: bool = False) -> List[float]:
    """Generates a 24-hour synthetic load profile with weekday/weekend shape + Gaussian noise."""
    base_load = [
        10.0, 9.0, 8.5, 8.5, 9.5, 12.0, 18.0, 24.0, 28.0, 29.0, 28.0, 26.0, 
        25.0, 24.0, 23.0, 24.0, 26.0, 29.0, 31.0, 30.0, 27.0, 22.0, 17.0, 12.0
    ]
    
    if is_weekend:
        # Flatten the curve a bit and shift peak
        base_load = [val * 0.85 + 2.0 for val in base_load]
    
    # Add noise
    synthetic = []
    for val in base_load:
        noise = random.gauss(0, val * 0.05)  # 5% standard deviation noise
        synthetic.append(max(0.0, val + noise))
        
    return synthetic
