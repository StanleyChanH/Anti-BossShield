from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="boss-sentinel",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="基于YOLOv8的Windows哨兵系统",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "opencv-python>=4.5.0",
        "ultralytics>=8.0.0",
        "facenet-pytorch>=2.5.0",
        "numpy>=1.21.0",
        "schedule>=1.1.0",
        "torch>=1.10.0",
        "torchvision>=0.11.0",
        "pywin32>=300",
        "Pillow>=9.0.0"
    ],
    entry_points={
        "console_scripts": [
            "boss-sentinel=boss_sentinel.main:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ]
)