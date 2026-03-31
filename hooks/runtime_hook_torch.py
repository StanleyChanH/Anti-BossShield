"""
PyTorch DLL 加载修复钩子
在导入 torch 之前设置正确的 DLL 搜索路径
"""
import os
import sys

# 获取临时解压目录
if hasattr(sys, '_MEIPASS'):
    torch_lib = os.path.join(sys._MEIPASS, 'torch', 'lib')
    if os.path.exists(torch_lib):
        # 将 torch lib 目录添加到 DLL 搜索路径
        os.add_dll_directory(torch_lib)
        # 同时添加到 PATH 环境变量
        os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
