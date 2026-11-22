import os
import maya.cmds as cmds
import pymel.core as pm
from functools import partial
import maya.api.OpenMaya as om

import NLTA_General
for module in [NLTA_General]:
    try:
        importlib.reload(module)
    except:
        from importlib import reload
        reload(module)


curveTemplates = {
    "cube": [
        [-0.5,  0.5,  0.5], [ 0.5,  0.5,  0.5], [ 0.5,  0.5, -0.5], [-0.5,  0.5, -0.5], 
        [-0.5,  0.5,  0.5], [-0.5, -0.5,  0.5], [ 0.5, -0.5,  0.5], [ 0.5,  0.5,  0.5], 
        [ 0.5, -0.5,  0.5], [ 0.5, -0.5, -0.5], [ 0.5,  0.5, -0.5], [ 0.5, -0.5, -0.5], 
        [-0.5, -0.5, -0.5], [-0.5,  0.5, -0.5], [-0.5, -0.5, -0.5], [-0.5, -0.5,  0.5]
    ],
    
    "sphere": [
        [0.0, 1.0, 0.0], [0.0, 0.924, -0.383], [0.0, 0.707, -0.707], [0.0, 0.383, -0.924], 
        [0.0, 0.0, -1.0], [0.0, -0.383, -0.924], [0.0, -0.707, -0.707], [0.0, -0.924, -0.383], 
        [0.0, -1.0, 0.0], [0.0, -0.924, 0.383], [0.0, -0.707, 0.707], [0.0, -0.383, 0.924], 
        [0.0, 0.0, 1.0], [0.0, 0.383, 0.924], [0.0, 0.707, 0.707], [0.0, 0.924, 0.383], 
        [0.0, 1.0, 0.0], [-0.383, 0.924, 0.0], [-0.707, 0.707, 0.0], [-0.924, 0.383, 0.0], 
        [-1.0, 0.0, 0.0], [-0.924, -0.383, 0.0], [-0.707, -0.707, 0.0], [-0.383, -0.924, 0.0], 
        [0.0, -1.0, 0.0], [0.383, -0.924, 0.0], [0.707, -0.707, 0.0], [0.924, -0.383, 0.0], 
        [1.0, 0.0, 0.0], [0.924, 0.383, 0.0], [0.707, 0.707, 0.0], [0.383, 0.924, 0.0], 
        [0.0, 1.0, 0.0], [0.0, 0.924, 0.383], [0.0, 0.707, 0.707], [0.0, 0.383, 0.924], 
        [0.0, 0.0, 1.0], [-0.707, 0.0, 0.707], [-1.0, 0.0, 0.0], [-0.707, 0.0, -0.707], 
        [0.0, 0.0, -1.0], [0.707, 0.0, -0.707], [1.0, 0.0, 0.0], [0.707, 0.0, 0.707], 
        [0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [0.707, 0.0, -0.707], [1.0, 0.0, 0.0], 
        [-1.0, 0.0, 0.0], [-0.924, 0.383, 0.0], [-0.707, 0.707, 0.0], [-0.383, 0.924, 0.0], 
        [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]
    ],
    
    "diamond": [
        [0.0, 0.0, 0.866], [-0.866, 0.0, 0.0], [0.0, 0.0, -0.866], [0.866, 0.0, 0.0], 
        [0.0, 0.0, 0.866], [0.0, 1.0, 0.0], [-0.866, 0.0, 0.0], [0.0, -1.0, 0.0], 
        [0.866, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -0.866], [0.0, -1.0, 0.0], 
        [0.0, 0.0, 0.866]
    ],
    
    "locator": [
        [0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [0.0, 0.0, 0.0], [-1.0, 0.0, 0.0], 
        [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]
    ],
    
    "eye": [
        [-1.777, 0.0, 0.0], [-1.756, -0.135, 0.0], [-1.715, -0.406, 0.0], [-1.401, -0.706, 0.0], 
        [-1.013, -0.807, 0.0], [-0.546, -0.727, 0.0], [-0.473, -0.321, 0.0], [0.473, -0.321, 0.0], 
        [0.546, -0.727, 0.0], [1.013, -0.807, 0.0], [1.403, -0.706, 0.0], [1.705, -0.406, 0.0], 
        [1.812, 0.0, 0.0], [1.705, 0.406, 0.0], [1.403, 0.706, 0.0], [1.013, 0.807, 0.0], 
        [0.546, 0.727, 0.0], [0.473, 0.321, 0.0], [-0.473, 0.321, 0.0], [-0.546, 0.727, 0.0], 
        [-1.013, 0.807, 0.0], [-1.401, 0.706, 0.0], [-1.715, 0.406, 0.0], [-1.756, 0.135, 0.0], 
        [-1.777, 0.0, 0.0]
    ],
    
    "circle": [
        [0.784, 0.0, -0.784], [0.0, 0.0, -1.108], [-0.784, 0.0, -0.784], [-1.108, 0.0, 0.0], 
        [-0.784, 0.0, 0.784], [0.0, 0.0, 1.108], [0.784, 0.0, 0.784], [1.108, 0.0, 0.0]
    ],
    
    "circle_rotate": [
        [-0.703, 0.0, 0.229], [-0.641, 0.0, 0.466], [-0.49, 0.0, 0.675], [-0.269, 0.0, 0.827], 
        [0.0, 0.0, 0.87], [0.269, 0.0, 0.827], [0.511, 0.0, 0.704], [0.704, 0.0, 0.511], 
        [0.827, 0.0, 0.269], [0.867, 0.0, 0.073], [1.054, 0.0, 0.045], [0.703, 0.0, -0.229], 
        [0.641, 0.0, -0.466], [0.49, 0.0, -0.675], [0.269, 0.0, -0.827], [0.0, 0.0, -0.87], 
        [-0.269, 0.0, -0.827], [-0.511, 0.0, -0.704], [-0.704, 0.0, -0.511], [-0.827, 0.0, -0.269], 
        [-0.867, 0.0, -0.073], [-1.054, 0.0, -0.045], [-0.703, 0.0, 0.229], [-0.74, 0.0, 0.0], 
        [-0.703, 0.0, -0.229], [-0.598, 0.0, -0.435], [-0.435, 0.0, -0.598], [-0.229, 0.0, -0.703], 
        [0.0, 0.0, -0.74], [0.229, 0.0, -0.703], [0.434, 0.0, -0.598], [0.598, 0.0, -0.435], 
        [0.703, 0.0, -0.229], [0.74, 0.0, 0.0], [0.703, 0.0, 0.229], [0.598, 0.0, 0.435], 
        [0.435, 0.0, 0.598], [0.229, 0.0, 0.703], [0.0, 0.0, 0.74], [-0.229, 0.0, 0.703], 
        [-0.435, 0.0, 0.598], [-0.598, 0.0, 0.435], [-0.703, 0.0, 0.229]
    ],
    
    "circle_point_shoulder": [
        [0.0, 1.0, -5.0], [-0.309, 0.951, -5.0], [-0.588, 0.809, -5.0], [-0.809, 0.588, -5.0], 
        [-0.951, 0.309, -5.0], [-1.0, 0.0, -5.0], [-0.951, -0.309, -5.0], [-0.809, -0.588, -5.0], 
        [-0.588, -0.809, -5.0], [-0.309, -0.951, -5.0], [0.0, -1.0, -5.0], [0.309, -0.951, -5.0], 
        [0.588, -0.809, -5.0], [0.809, -0.588, -5.0], [0.951, -0.309, -5.0], [1.0, 0.0, -5.0], 
        [0.951, 0.309, -5.0], [0.809, 0.588, -5.0], [0.588, 0.809, -5.0], [0.309, 0.951, -5.0], 
        [0.0, 1.0, -5.0], [0.0, -1.0, -5.0], [0.0, 0.0, -5.0], [0.0, 0.0, 0.0]
    ],
    
    "circle_point_finger": [
        [0.0, 3.0, 0.0], [0.0, 3.134, 0.5], [0.0, 3.5, 0.866], [0.0, 4.0, 1.0], 
        [0.0, 4.5, 0.866], [0.0, 4.866, 0.5], [0.0, 5.0, 0.0], [0.0, 4.866, -0.5], 
        [0.0, 4.5, -0.866], [0.0, 4.0, -1.0], [0.0, 3.5, -0.866], [0.0, 3.134, -0.5], 
        [0.0, 3.0, 0.0], [0.0, 3.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 0.0]
    ],
    
    "translate": [
        [-2.0, 4.0, 0.0], [-2.0, 2.0, 0.0], [-4.0, 2.0, 0.0], [-4.0, 3.0, 0.0], 
        [-6.0, 0.0, 0.0], [-4.0, -3.0, 0.0], [-4.0, -2.0, 0.0], [-2.0, -2.0, 0.0], 
        [-2.0, -4.0, 0.0], [-3.0, -4.0, 0.0], [0.0, -6.0, 0.0], [3.0, -4.0, 0.0], 
        [2.0, -4.0, 0.0], [2.0, -2.0, 0.0], [4.0, -2.0, 0.0], [4.0, -3.0, 0.0], 
        [6.0, 0.0, 0.0], [4.0, 3.0, 0.0], [4.0, 2.0, 0.0], [2.0, 2.0, 0.0], 
        [2.0, 4.0, 0.0], [3.0, 4.0, 0.0], [0.0, 6.0, 0.0], [-3.0, 4.0, 0.0], 
        [-2.0, 4.0, 0.0]
    ],
    
    "translate_forward_back": [
        [-4.0, 0.0, 0.0], [-2.0, 2.0, 0.0], [-2.0, 1.0, 0.0], [2.0, 1.0, 0.0], 
        [2.0, 2.0, 0.0], [4.0, 0.0, 0.0], [2.0, -2.0, 0.0], [2.0, -1.0, 0.0], 
        [-2.0, -1.0, 0.0], [-2.0, -2.0, 0.0], [-4.0, 0.0, 0.0]
    ],
    
    "rotate_point": [
        [0.0, 0.0, 0.0], [0.023, 1.306, 0.0], [0.231, 1.273, 0.0], [0.439, 1.167, 0.0], 
        [0.522, 1.084, 0.0], [0.464, 1.028, 0.0], [0.707, 1.076, 0.0], [0.771, 1.34, 0.0], 
        [0.698, 1.261, 0.0], [0.588, 1.372, 0.0], [0.309, 1.514, 0.0], [0.0, 1.561, 0.0], 
        [-0.309, 1.514, 0.0], [-0.588, 1.372, 0.0], [-0.698, 1.261, 0.0], [-0.771, 1.34, 0.0], 
        [-0.707, 1.076, 0.0], [-0.464, 1.028, 0.0], [-0.522, 1.084, 0.0], [-0.439, 1.167, 0.0], 
        [-0.231, 1.273, 0.0], [-0.023, 1.306, 0.0], [0.0, 0.0, 0.0]
    ],
    
    "switch_ik_fk": [
        [-0.841, -0.043, 0.0], [-0.806, 0.262, 0.0], [-0.688, 0.043, 0.0], [-0.661, 0.215, 0.0], 
        [-0.562, 0.408, 0.0], [-0.408, 0.562, 0.0], [-0.215, 0.661, 0.0], [0.0, 0.695, 0.0], 
        [0.215, 0.661, 0.0], [0.408, 0.562, 0.0], [0.562, 0.408, 0.0], [0.661, 0.215, 0.0], 
        [0.841, 0.043, 0.0], [0.806, -0.262, 0.0], [0.688, -0.043, 0.0], [0.661, -0.215, 0.0], 
        [0.562, -0.408, 0.0], [0.408, -0.562, 0.0], [0.215, -0.661, 0.0], [0.0, -0.695, 0.0], 
        [-0.215, -0.661, 0.0], [-0.408, -0.562, 0.0], [-0.562, -0.408, 0.0], [-0.661, -0.215, 0.0], 
        [-0.841, -0.043, 0.0], [-0.951, -0.309, 0.0], [-0.809, -0.588, 0.0], [-0.588, -0.809, 0.0], 
        [-0.309, -0.951, 0.0], [0.0, -1.0, 0.0], [0.309, -0.951, 0.0], [0.588, -0.809, 0.0], 
        [0.809, -0.588, 0.0], [0.951, -0.309, 0.0], [0.993, -0.043, 0.0], [0.806, -0.262, 0.0], 
        [0.841, 0.043, 0.0], [0.951, 0.309, 0.0], [0.809, 0.588, 0.0], [0.588, 0.809, 0.0], 
        [0.309, 0.951, 0.0], [0.0, 1.0, 0.0], [-0.309, 0.951, 0.0], [-0.588, 0.809, 0.0], 
        [-0.809, 0.588, 0.0], [-0.951, 0.309, 0.0], [-0.993, 0.043, 0.0], [-0.806, 0.262, 0.0]
    ],    
    "finger_diamon_part1": [
        [0.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 4.0, 1.0], [0.0, 5.0, 0.0], 
        [0.0, 4.0, -1.0], [0.0, 3.0, 0.0], [-1.0, 4.0, 0.0], [0.0, 5.0, 0.0], 
        [1.0, 4.0, 0.0], [0.0, 3.0, 0.0], [-1.0, 4.0, 0.0], [0.0, 4.0, 1.0], 
        [1.0, 4.0, 0.0], [0.0, 4.0, -1.0], [-1.0, 4.0, 0.0]
    ],    
    "setting": [
        [0.258, 0.966, 0.0], [0.258, 1.166, 0.0], [-0.259, 1.166, 0.0], [-0.259, 0.966, 0.0], 
        [-0.22, 0.821, 0.0], [0.22, 0.821, 0.0], [0.258, 0.966, 0.0], [-0.259, 0.966, 0.0], 
        [-0.707, 0.707, 0.0], [-0.602, 0.601, 0.0], [-0.821, 0.22, 0.0], [-0.966, 0.258, 0.0], 
        [-1.139, 0.358, 0.0], [-0.881, 0.807, 0.0], [-0.707, 0.707, 0.0], [-0.966, 0.258, 0.0], 
        [-0.821, 0.22, 0.0], [-0.821, -0.22, 0.0], [-0.966, -0.259, 0.0], [-0.966, 0.258, 0.0], 
        [-0.966, -0.259, 0.0], [-1.139, -0.359, 0.0], [-0.88, -0.807, 0.0], [-0.707, -0.707, 0.0], 
        [-0.601, -0.602, 0.0], [-0.821, -0.22, 0.0], [-0.966, -0.259, 0.0], [-0.707, -0.707, 0.0], 
        [-0.258, -0.966, 0.0], [-0.22, -0.821, 0.0], [-0.601, -0.602, 0.0], [-0.22, -0.821, 0.0], 
        [0.22, -0.821, 0.0], [0.259, -0.966, 0.0], [0.259, -1.166, 0.0], [-0.258, -1.166, 0.0], 
        [-0.258, -0.966, 0.0], [0.259, -0.966, 0.0], [0.707, -0.707, 0.0], [0.602, -0.601, 0.0], 
        [0.22, -0.821, 0.0], [0.602, -0.601, 0.0], [0.821, -0.22, 0.0], [0.966, -0.258, 0.0], 
        [1.139, -0.358, 0.0], [0.881, -0.807, 0.0], [0.707, -0.707, 0.0], [0.966, -0.258, 0.0], 
        [0.966, 0.259, 0.0], [0.821, 0.22, 0.0], [0.821, -0.22, 0.0], [0.821, 0.22, 0.0], 
        [0.601, 0.602, 0.0], [0.707, 0.707, 0.0], [0.88, 0.807, 0.0], [1.139, 0.359, 0.0], 
        [0.966, 0.259, 0.0], [0.707, 0.707, 0.0], [0.258, 0.966, 0.0], [0.22, 0.821, 0.0], 
        [0.601, 0.602, 0.0], [0.22, 0.821, 0.0], [-0.22, 0.821, 0.0], [-0.602, 0.601, 0.0]
    ],
    
    "arc_half_rotate": [
        [0.0, 0.0, 0.917], [0.179, 0.0, 0.614], [0.232, 0.0, 0.714], [0.442, 0.0, 0.608], 
        [0.608, 0.0, 0.442], [0.714, 0.0, 0.232], [0.751, 0.0, 0.0], [0.714, 0.0, -0.232], 
        [0.608, 0.0, -0.442], [0.442, 0.0, -0.608], [0.232, 0.0, -0.714], [0.179, 0.0, -0.614], 
        [0.0, 0.0, -0.918], [0.308, 0.0, -1.06], [0.309, 0.0, -0.951], [0.588, 0.0, -0.809], 
        [0.809, 0.0, -0.588], [0.951, 0.0, -0.309], [1.0, 0.0, 0.0], [0.951, 0.0, 0.309], 
        [0.809, 0.0, 0.588], [0.588, 0.0, 0.809], [0.309, 0.0, 0.951], [0.308, 0.0, 1.06], 
        [0.0, 0.0, 0.917]
    ],
    
    "main_control": [
        [4.093, 0.0, -1.264], [3.698, 0.0, -1.201], [3.145, 0.0, -2.285], [2.285, 0.0, -3.145], 
        [1.201, 0.0, -3.698], [1.264, 0.0, -4.093], [1.758, 0.0, -4.014], [0.0, 0.0, -4.9], 
        [-1.758, 0.0, -4.014], [-1.264, 0.0, -4.093], [-1.201, 0.0, -3.698], [-2.285, 0.0, -3.145], 
        [-3.145, 0.0, -2.285], [-3.698, 0.0, -1.201], [-4.093, 0.0, -1.264], [-4.014, 0.0, -1.758], 
        [-4.9, 0.0, 0.0], [-4.014, 0.0, 1.758], [-4.093, 0.0, 1.264], [-3.698, 0.0, 1.201], 
        [-3.145, 0.0, 2.285], [-2.285, 0.0, 3.145], [-1.201, 0.0, 3.698], [-1.264, 0.0, 4.093], 
        [-1.758, 0.0, 4.014], [0.0, 0.0, 4.9], [1.758, 0.0, 4.014], [1.264, 0.0, 4.093], 
        [1.201, 0.0, 3.698], [2.285, 0.0, 3.145], [3.145, 0.0, 2.285], [3.698, 0.0, 1.201], 
        [4.093, 0.0, 1.264], [4.014, 0.0, 1.758], [4.9, 0.0, 0.0], [4.014, 0.0, -1.758], 
        [4.093, 0.0, -1.264], [3.698, 0.0, -1.201], [3.384, 0.0, -1.099], [3.558, 0.0, 0.0], 
        [3.384, 0.0, 1.099], [3.698, 0.0, 1.201], [3.384, 0.0, 1.099], [2.878, 0.0, 2.091], 
        [2.091, 0.0, 2.878], [1.099, 0.0, 3.384], [1.201, 0.0, 3.698], [1.099, 0.0, 3.384], 
        [0.0, 0.0, 3.558], [-1.099, 0.0, 3.384], [-1.201, 0.0, 3.698], [-1.099, 0.0, 3.384], 
        [-2.091, 0.0, 2.878], [-2.878, 0.0, 2.091], [-3.384, 0.0, 1.099], [-3.698, 0.0, 1.201], 
        [-3.384, 0.0, 1.099], [-3.558, 0.0, 0.0], [-3.384, 0.0, -1.099], [-3.698, 0.0, -1.201], 
        [-3.384, 0.0, -1.099], [-2.878, 0.0, -2.091], [-2.091, 0.0, -2.878], [-1.099, 0.0, -3.384], 
        [-1.201, 0.0, -3.698], [-1.099, 0.0, -3.384], [0.0, 0.0, -3.558], [1.099, 0.0, -3.384], 
        [1.201, 0.0, -3.698], [1.099, 0.0, -3.384], [2.091, 0.0, -2.878], [2.878, 0.0, -2.091], 
        [3.384, 0.0, -1.099]
    ],
    "quare":[
        [-2,0,2], [2,0,2], [2,0,-2], [-2,0,-2], [-2,0,2]
    ]
}



def IndexColorPick(data,*arr):
    colors_dict = {
        "Gray": (0, 0.17, 0.17, 0.17), "Black": (1, 0.0, 0.0, 0.0), "Dark Gray": (2, 0.25, 0.25, 0.25), "Light Gray": (3, 0.5, 0.5, 0.5),
        "Dark Red": (4, 0.61, 0.0, 0.0), "Dark Blue": (5, 0.0, 0.0, 0.3), "Blue": (6, 0.0, 0.0, 1.0), "Dark Green": (7, 0.0, 0.3, 0.0),
        "Dark purple": (8, 0.15, 0.0, 0.3), "Pink": (9, 0.9, 0.0, 0.9), "Brown": (10, 0.3, 0.1, 0.0), "Dark Brown": (11, 0.15, 0.05, 0.0),
        "Light Brown": (12, 0.66, 0.3, 0.1), "Red": (13, 1.0, 0.0, 0.0), "Light Green": (14, 0.0, 1.0, 0.0), "Dark Blue (Alt)": (15, 0.0, 0.0, 0.6),
        "White": (16, 1.0, 1.0, 1.0), "Yellow": (17, 1.0, 1.0, 0.0), "Cyan": (18, 0.0, 1.0, 1.0), "Jade": (19, 0.0, 1.0, 0.5),
        "Soft Pink": (20, 1.0, 0.71, 0.76), "Latte": (21, 0.9, 0.76, 0.5), "Light Yellow": (22, 1.0, 1.0, 0.6), "Middle Green": (23, 0.2, 0.8, 0.2),
        "Middle Brown": (24, 0.55, 0.27, 0.07), "Middle Yellow": (25, 1.0, 0.84, 0.0), "Little Green": (26, 0.6, 0.98, 0.6), "Little Jade": (27, 0.5, 1.0, 0.83),
        "Little Cyan": (28, 0.88, 1.0, 1.0), "Little Blue": (29, 0.69, 0.93, 0.93), "Little Purple": (30, 0.9, 0.9, 0.98), "Little Pink": (31, 1.0, 0.94, 0.96),
    }
    palette = cmds.palettePort(dimensions=(8,4),transparent=0,colorEditable=False,parent =data.get("parent"),height=data.get("height",100),width=data.get("width",100))
    for name, data in colors_dict.items():
        idx = data[0]
        r, g, b = data[1], data[2], data[3]
        cmds.palettePort(palette, edit=True, rgb=(idx, r, g, b))
    cmds.palettePort(palette, edit=True, cc=lambda: IndexColorChange(palette))
    return(palette)

def IndexColorChange(palette_name,*arr):
    color = cmds.palettePort(palette_name, query=True, scc=True)
    objs = cmds.ls(selection=True)        
    for obj in objs:
        objectType = cmds.objectType(obj)
        if objectType in ["transform","joint"]:
            shapes = cmds.listRelatives(obj,shapes=True,path=True)
            for shape in shapes:
                cmds.setAttr(shape+".overrideEnabled",True)
                cmds.setAttr(shape+".overrideColor",color)
        else:
            cmds.setAttr(obj+".overrideEnabled",True)
            cmds.setAttr(obj+".overrideColor",color)

def ShapePick(parentUI, *arr):
    palette = cmds.rowColumnLayout(adjustableColumn=True, parent=parentUI,nc=5)
    for name in curveTemplates.keys():
        cmds.button(
            label=name,
            command=lambda x, n=name: ShapeChange(n)
        )
    return palette

def ShapeASData(*arr):
    return(["Gear","SphereFourArrows","CircleFourArrows","CircleThreeArrows","CircleTwoArrows","CircleOneArrows","OneArrowThin",
    "OneArrow","TwoArrowsCurvedThin","TwoArrowsCurved","TwoArrowsThin","TwoArrow","FourArrowsCurvedThin","FourArrowsCurved",
    "FourArrowsThin","FourArrows","Locator","CrossThin","Cross","SphereDumbbell","SquareDumbbell","CircelDumbbell",
    "SpherePin","SquarePin","CirclePin","Diamond","Pyramid","Box","HalfSphere","Sphere","Triangle","Square",
    "HalfCircle","Circle"])


def ShapeData(*arr):
    return(curveTemplates)

def ShapeChangeSingle(data, *arr):
    shape = data["shape"]
    objs = data["objs"]
    if shape not in curveTemplates:
        cmds.warning("Shape not found: " + shape)
        return
    points = curveTemplates[shape]
    for obj in objs:
        if cmds.objExists(obj):
            if cmds.nodeType(obj) == "nurbsCurve":
                shape = obj
                transform = cmds.listRelatives(shape, p=True, f=True)[0]
            else:
                transform = obj
                shapes = cmds.listRelatives(transform,s=True,type="nurbsCurve",f=True) or []
                if not shapes:
                    cmds.warning("No curve shape found under: " + transform)
                    continue
                shape = shapes[0]

            if not cmds.objExists(shape):
                continue
            incoming = cmds.listConnections(shape,s=True,d=False,p=True,c=True) or []
            outgoing = cmds.listConnections(shape,s=False,d=True,p=True,c=True) or []
            cmds.delete(shape)

            new_curve = cmds.curve(d=1,p=points,name=transform.split("|")[-1] + "_crvTmp")
            new_shape = cmds.listRelatives(new_curve,s=True,f=True)[0]
            cmds.parent(new_shape,transform,shape=True,r=True)
            cmds.delete(new_curve)
            new_shape = cmds.listRelatives(transform,s=True,type="nurbsCurve",f=True)[-1]

            for i in range(0, len(incoming), 2):
                dst_attr = incoming[i]
                src_attr = incoming[i + 1]
                dst_attr = dst_attr.replace(shape,new_shape)
                try:
                    cmds.connectAttr(src_attr,dst_attr,f=True)
                except:
                    pass

            for i in range(0, len(outgoing), 2):
                src_attr = outgoing[i]
                dst_attr = outgoing[i + 1]
                src_attr = src_attr.replace(shape,new_shape)
                try:
                    cmds.connectAttr(src_attr,dst_attr,f=True)
                except:
                    pass
            cmds.rename(new_shape,shape.split("|")[-1])


def MirrorShape(*arr):
    sel = cmds.ls(sl=True)     
    sel01 = cmds.listRelatives(sel[0])
    sel02 = cmds.listRelatives(sel[1])     
    length = len(sel02)     
    for i in range(length):
        shape01 = cmds.ls(sel01[i] + ".cv[*]", fl=True)
        shape02 = cmds.ls(sel02[i] + ".cv[*]", fl=True)        
        y = 0               
        for a in shape02:
            ListXYZ = cmds.pointPosition(shape01[y], w=True)
            cmds.move(-ListXYZ[0], ListXYZ[1], ListXYZ[2], a, ws=True)
            y = y + 1

def CopyShape(*arr):
    selection = cmds.ls(selection=True, allPaths=True)
    if len(selection) > 1:
        shape_from = selection[0]
        shape_from_pivot = cmds.xform(shape_from, q=True, r=True, rp=True, ws=True)
        selection.remove(selection[0])
        shape_to = selection
        for i in shape_to:            
            object_pivot = cmds.xform(i, q=True, r=True, rp=True, ws=True)
            
            cmds.select(i + ".cv[*]")
            cluster_name = cmds.cluster()
            pivot_temp = cmds.xform(cluster_name, q=True, r=True, rp=True, ws=True)
            cmds.xform(i, a=True, rp=pivot_temp, ws=True)
            cmds.delete(cluster_name)
            
            copy = cmds.duplicate(shape_from, rr=True)[0]
            
            group_temp = cmds.group(em=True)
            contraint_temp = cmds.parentConstraint(i, group_temp, mo=False)
            cmds.matchTransform(copy, i, pos=True)
            cmds.parent(copy, group_temp)
            if cmds.listRelatives(copy, ad=True, type="transform", path=True):
                cmds.delete(cmds.listRelatives(copy, ad=True, type="transform", path=True))                
            try:
                cmds.makeIdentity(copy, apply=True, t=1, r=0, s=0, n=0)
            except (Exception):
                pass
                
            try:
                cmds.makeIdentity(copy, apply=True, t=0, r=1, s=0, n=0)
            except (Exception):
                pass
                
            try:
                cmds.makeIdentity(copy, apply=True, t=0, r=0, s=1, n=0)
            except (Exception):
                pass
                
            shape_new = cmds.listRelatives(copy, shapes=True, fullPath=True)
            for a in shape_new:
                array_connection = cmds.listConnections(a, plugs=True, connections=True)
                if array_connection:
                    b = 0
                    while (b < len(array_connection)):
                        cmds.disconnectAttr(array_connection[b], array_connection[b + 1])
                        b += 2

            old_shapes = cmds.listRelatives(i, shapes=True, fullPath=True) or []
            old_shape_names = [cmds.ls(s, sn=True)[0] for s in old_shapes]
            cmds.select(clear=True)
            cmds.select(shape_new, add=True)
            cmds.select(i, add=True)
            pm.mel.eval("parent -r -s")

            all_shapes = cmds.listRelatives(i, shapes=True, fullPath=True) or []
            shape_new_array = [s for s in all_shapes if s not in old_shapes]

            # Lưu các connection cần reconnect
            connsData = []
            attrsReconns = ['visibility']

            for attr in attrsReconns:
                if old_shapes:
                    src = cmds.connectionInfo(
                        old_shapes[0] + "." + attr,
                        sourceFromDestination=True
                    )
                    if src:
                        connsData.append([src, attr])

            # Xóa shape cũ
            for shape in old_shapes:
                cmds.lockNode(shape, lock=False)
                cmds.delete(shape)

            # Đổi tên shape mới thành tên shape cũ
            for new_shape, old_name in zip(shape_new_array, old_shape_names):
                cmds.rename(new_shape, old_name)

            # Lấy lại shape sau khi rename
            shape_new_array = cmds.listRelatives(i, shapes=True, fullPath=True) or []

            # Reconnect
            for src, attr in connsData:
                for shapeNew in shape_new_array:
                    cmds.connectAttr(src, shapeNew + "." + attr, force=True)
            
            cmds.xform(i, a=True, rp=object_pivot, ws=True)
            cmds.delete(group_temp)
            cmds.select(i)
    else:
        cmds.confirmDialog(title="Confirm", message="Please more than two shape", button=["Yes"], defaultButton="Yes", cancelButton="Yes")

def QuickExportCurve(data,*arr):
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        folder_temp = pm.mel.eval("SaveSceneAs;")
    folder_temp = os.path.dirname(pm.sceneName())
    if not folder_temp:
        return
    data_temp = {}
    selection = cmds.ls(selection=True, long=True)
    allAsCtrl = []
    if selection:
        for obj in selection:
            if cmds.nodeType(obj) == "transform":
                if cmds.listRelatives(obj,children=True,type="nurbsCurve"):
                    if obj not in allAsCtrl:
                        allAsCtrl.append(obj)

    else:
        allAsCtrlTemp = cmds.ls( type="nurbsCurve",ap=True)
        for curve in allAsCtrlTemp:
            transformNode = cmds.listRelatives(curve,parent=True,pa=True)[0]
            if transformNode not in allAsCtrl:
                allAsCtrl.append(transformNode)

    # Export
    for ctrl in allAsCtrl:
        data_temp[ctrl] = {}
        data_temp[ctrl]["overrideEnabled"] = cmds.getAttr(ctrl + ".overrideEnabled")
        data_temp[ctrl]["overrideRGBColors"] = cmds.getAttr(ctrl + ".overrideRGBColors")
        data_temp[ctrl]["visibility"] = cmds.getAttr(ctrl + ".visibility")
        if data_temp[ctrl]["overrideRGBColors"] == 1:
            data_temp[ctrl]["overrideColorR"] = cmds.getAttr(ctrl + ".drawOverride.overrideColorR")
            data_temp[ctrl]["overrideColorG"] = cmds.getAttr(ctrl + ".drawOverride.overrideColorG")
            data_temp[ctrl]["overrideColorB"] = cmds.getAttr(ctrl + ".drawOverride.overrideColorB")
        else:
            data_temp[ctrl]["overrideColor"] = cmds.getAttr(ctrl + ".overrideColor")

        # Curve shapes
        curveShapes = cmds.listRelatives(ctrl,children=True,type="nurbsCurve",pa=True)
        if curveShapes:
            curveData = {}
            for curveChild in curveShapes:
                if "Orig" in curveChild:
                    continue
                curveChildName = curveChild.split("|")[-1]
                curveData[curveChildName] = {}

                # Curve attributes
                curveData[curveChildName]["degree"] = cmds.getAttr(curveChild + ".degree")
                curveData[curveChildName]["form"] = cmds.getAttr(curveChild + ".form")


                # CV positions
                pointData = {}
                points = cmds.ls(curveChild + ".controlPoints[*]",flatten=True)
                for point in points:
                    if not cmds.objExists(point):
                        continue
                    pointName = point.split("|")[-1]
                    pointName = pointName.split(".")[-1]
                    pointData[pointName] = cmds.xform(point,q=True,os=True,t=True)
                curveData[curveChildName]["pointData"] = pointData


                # Curve information
                sel = om.MSelectionList()
                sel.add(curveChild)
                dagPath = sel.getDagPath(0)
                fnCurve = om.MFnNurbsCurve(dagPath)
                curveData[curveChildName]["degree"] = fnCurve.degree
                curveData[curveChildName]["form"] = int(fnCurve.form)
                knots = fnCurve.knots()
                curveData[curveChildName]["knots"] = [float(knot) for knot in knots]

                # Curve display attributes
                curveData[curveChildName]["overrideEnabled"] = cmds.getAttr(curveChild + ".overrideEnabled")
                curveData[curveChildName]["overrideRGBColors"] = cmds.getAttr(curveChild + ".overrideRGBColors")
                curveData[curveChildName]["visibility"] = cmds.getAttr(curveChild + ".visibility")
                if curveData[curveChildName]["overrideRGBColors"] == 1:
                    curveData[curveChildName]["overrideColorR"] = cmds.getAttr(curveChild + ".drawOverride.overrideColorR")
                    curveData[curveChildName]["overrideColorG"] = cmds.getAttr(curveChild + ".drawOverride.overrideColorG")
                    curveData[curveChildName]["overrideColorB"] = cmds.getAttr(curveChild + ".drawOverride.overrideColorB")
                else:
                    curveData[curveChildName]["overrideColor"] = cmds.getAttr(curveChild + ".overrideColor")
            data_temp[ctrl]["curveData"] = curveData


        # Special data
        if ctrl == "HipSwinger_M":
            offsetGroup = cmds.listRelatives(ctrl,parent=True)[0]
            data_temp[ctrl]["translate"] = (
                cmds.getAttr(offsetGroup + ".translateX"),
                cmds.getAttr(offsetGroup + ".translateY"),
                cmds.getAttr(offsetGroup + ".translateZ")
            )

    # Save JSON
    file_path = data["sceneDataPath"]+ "dataCurveShape.json"
    NLTA_General.writeJsonFile(file_path,data_temp)
    print("Url export: " + file_path)


def RebuildCurveShape(ctrl, curveChild, curveData):
    pointData = curveData.get("pointData", {})
    if not pointData:
        return None

    # Get curve information
    degree = curveData.get("degree", 3)
    form = curveData.get("form", 0)
    knots = curveData.get("knots", [])

    # Get CV positions
    points = []
    sortedPoints = sorted(pointData.items(),key=lambda x: int(x[0].split("[")[-1].split("]")[0]))
    for pointName, position in sortedPoints:
        points.append(position)
    if len(points) < degree + 1:
        print("Cannot rebuild curve '{}': not enough CVs.".format(curveChild))
        return None


    # Create temporary curve
    tempCurve = None
    try:
        tempCurve = cmds.curve(degree=degree,point=points,name=ctrl + "_TempCurve")
        tempShape = cmds.listRelatives( tempCurve,shapes=True,fullPath=True)[0]

        # Try to restore form
        if form != 0:
            try:
                cmds.setAttr(tempShape + ".form",form)
            except:
                pass

        # Replace old shape
        oldShapePath = ctrl + "|" + curveChild
        if cmds.objExists(oldShapePath):
            cmds.delete(oldShapePath)

        # Parent new shape under controller
        newShape = cmds.parent(tempShape,ctrl,shape=True,relative=True)[0]

        # Rename shape to original name
        newShape = cmds.rename(newShape,curveChild)

        # Restore curve attributes
        try:
            cmds.setAttr(newShape + ".overrideEnabled",curveData["overrideEnabled"])
        except:
            pass

        try:
            cmds.setAttr(newShape + ".overrideRGBColors",curveData["overrideRGBColors"])
        except:
            pass

        try:
            cmds.setAttr(newShape + ".visibility",curveData["visibility"])
        except:
            pass

        if curveData.get("overrideRGBColors") == 1:
            try:
                cmds.setAttr(newShape + ".drawOverride.overrideColorR",curveData["overrideColorR"])
                cmds.setAttr(newShape + ".drawOverride.overrideColorG",curveData["overrideColorG"])
                cmds.setAttr(newShape + ".drawOverride.overrideColorB",curveData["overrideColorB"])
            except:
                pass
        else:
            try:
                cmds.setAttr(newShape + ".overrideColor",curveData["overrideColor"])
            except:
                pass
        return newShape

    finally:
        if tempCurve and cmds.objExists(tempCurve):
            cmds.delete(tempCurve)


def QuickImportCurve(data,*arr):
    folderTemp = os.path.dirname(pm.sceneName())
    if not folderTemp:
        folderTemp = pm.mel.eval("SaveSceneAs;")
    filePath = data["sceneDataPath"] + "dataCurveShape.json"

    if not os.path.exists(filePath):
        print("Curve data not found: {}".format(filePath))
        return

    dataTemp = NLTA_General.readJsonFile(filePath)
    if not dataTemp:
        return

    # Controllers
    selection = cmds.ls(selection=True,long=True)
    if selection:
        ctrls = selection
    else:
        ctrls = list(dataTemp.keys())


    # Import
    for ctrl in ctrls:
        if ctrl not in dataTemp:
            continue
        if not cmds.objExists(ctrl):
            continue
        ctrlData = dataTemp[ctrl]
        try:
            cmds.setAttr(ctrl + ".overrideEnabled",ctrlData["overrideEnabled"])
            cmds.setAttr(ctrl + ".overrideRGBColors",ctrlData["overrideRGBColors"])
        except:
            pass

        try:
            cmds.setAttr(ctrl + ".visibility",ctrlData["visibility"])
        except:
            pass

        if ctrlData.get("overrideRGBColors") == 1:
            try:
                cmds.setAttr(ctrl + ".drawOverride.overrideColorR",ctrlData["overrideColorR"])
                cmds.setAttr(ctrl + ".drawOverride.overrideColorG",ctrlData["overrideColorG"])
                cmds.setAttr(ctrl + ".drawOverride.overrideColorB",ctrlData["overrideColorB"])
            except:
                pass
        else:
            try:
                cmds.setAttr(ctrl + ".overrideColor",ctrlData["overrideColor"])
            except:
                pass


        # Curve data
        curveData = ctrlData.get("curveData",{})

        if not curveData:
            continue

        for curveChild, curveChildData in curveData.items():
            curveChildPath = ctrl + "|" + curveChild
            pointData = curveChildData.get("pointData",{})

            # Shape exists?
            if cmds.objExists(curveChildPath):
                currentPoints = cmds.ls(curveChildPath + ".controlPoints[*]",flatten=True)
                savedPoints = list(pointData.keys())

                # Same CV count
                if len(currentPoints) == len(savedPoints):
                    for point in savedPoints:
                        pointPath = (curveChildPath+ "."+ point)
                        if cmds.objExists(pointPath):
                            try:
                                cmds.xform(pointPath,os=True,translation=pointData[point])
                            except:
                                pass

                    # Restore curve attributes
                    try:
                        cmds.setAttr(curveChildPath + ".overrideEnabled",curveChildData["overrideEnabled"])
                        cmds.setAttr(curveChildPath + ".overrideRGBColors",curveChildData["overrideRGBColors"])
                    except:
                        pass

                    if curveChildData.get( "overrideRGBColors") == 1:
                        try:
                            cmds.setAttr(curveChildPath + ".drawOverride.overrideColorR",curveChildData["overrideColorR"])
                            cmds.setAttr( curveChildPath + ".drawOverride.overrideColorG",curveChildData["overrideColorG"])
                            cmds.setAttr(curveChildPath + ".drawOverride.overrideColorB",curveChildData["overrideColorB"])
                        except:
                            pass
                    else:
                        try:
                            cmds.setAttr(curveChildPath + ".overrideColor",curveChildData["overrideColor"])
                        except:
                            pass

                # Different CV count
                else:
                    print("Rebuilding curve: {}".format(curveChildPath))
                    RebuildCurveShape(ctrl,curveChild,curveChildData)

            # Shape does not exist
            else:
                print("Curve shape not found, rebuilding: {}".format(curveChildPath))
                RebuildCurveShape(ctrl,curveChild,curveChildData)
    cmds.select(clear=True)

def ImportCurveFromFile(*arr):
    result = cmds.fileDialog2(fileMode=1,caption="Select Curve Shape JSON",fileFilter="JSON Files (*.json)")
    if not result:
        return
    filePath = result[0]
    dataTemp = NLTA_General.readJsonFile(filePath)
    for ctrl in dataTemp:
        if cmds.objExists(ctrl):
            try:
                cmds.setAttr(ctrl+".overrideEnabled",dataTemp[ctrl]["overrideEnabled"])
                cmds.setAttr(ctrl+".overrideRGBColors",dataTemp[ctrl]["overrideRGBColors"])
            except:pass
            try:
                cmds.setAttr(ctrl+".visibility",dataTemp[ctrl]["visibility"])
            except:pass
            if dataTemp[ctrl]["overrideRGBColors"] == 1:
                cmds.setAttr(ctrl+".drawOverride.overrideColorR",dataTemp[ctrl]["overrideColorR"])
                cmds.setAttr(ctrl+".drawOverride.overrideColorG",dataTemp[ctrl]["overrideColorG"])
                cmds.setAttr(ctrl+".drawOverride.overrideColorB",dataTemp[ctrl]["overrideColorB"])
            else:
                try:
                    cmds.setAttr(ctrl+".overrideColor",dataTemp[ctrl]["overrideColor"])
                except:pass
        if dataTemp[ctrl]["curveData"]:
            for curveChild in dataTemp[ctrl]["curveData"]:
                curveChildPath = ctrl+"|"+curveChild
                if cmds.objExists(curveChildPath):
                    curveChildData = dataTemp[ctrl]["curveData"][curveChild]
                    try:                  
                        cmds.setAttr(curveChildPath+".overrideEnabled",curveChildData["overrideEnabled"])
                        cmds.setAttr(curveChildPath+".overrideRGBColors",curveChildData["overrideRGBColors"])
                    except:pass
                    try:
                        cmds.setAttr(curveChildPath+".visibility",curveChildData["visibility"])
                    except:pass
                    if curveChildData["overrideRGBColors"] == True:
                        cmds.setAttr(curveChildPath+".drawOverride.overrideColorR",curveChildData["overrideColorR"])
                        cmds.setAttr(curveChildPath+".drawOverride.overrideColorG",curveChildData["overrideColorG"])
                        cmds.setAttr(curveChildPath+".drawOverride.overrideColorB",curveChildData["overrideColorB"])
                    else:
                        try:
                            cmds.setAttr(curveChildPath+".overrideColor",curveChildData["overrideColor"])
                        except:pass
                    for point in curveChildData["pointData"]:
                        pointPath = curveChildPath+"."+point
                        if cmds.objExists(pointPath):
                            cmds.xform(pointPath,q=True,os=True,t=True)
                            cmds.xform(pointPath,os=True, translation=curveChildData["pointData"][point])
                            
