"""测试人脸检测器"""
import pytest
import sys
import os
import cv2
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from boss_sentinel.detector import FaceDetector


class TestFaceDetector:
    """测试FaceDetector类"""

    @pytest.fixture
    def detector(self):
        """创建检测器实例"""
        return FaceDetector(use_gpu=False)

    @pytest.fixture
    def sample_image(self):
        """创建示例图像"""
        # 创建一个640x480的空白图像
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        return img

    def test_detector_initialization(self, detector):
        """测试检测器初始化"""
        assert detector.model is not None
        assert detector.device == 'cpu'  # 因为use_gpu=False

    def test_detector_with_gpu(self):
        """测试GPU检测器初始化"""
        import torch
        if torch.cuda.is_available():
            detector = FaceDetector(use_gpu=True)
            assert detector.device.startswith('cuda')
        else:
            # 如果没有GPU，应该回退到CPU
            detector = FaceDetector(use_gpu=True)
            assert detector.device == 'cpu'

    def test_detect_no_faces(self, detector, sample_image):
        """测试检测没有人脸的图像"""
        boxes = detector.detect(sample_image, confidence_threshold=0.7)
        # 空白图像应该检测不到人脸
        assert boxes is None or len(boxes) == 0

    def test_detect_with_low_threshold(self, detector, sample_image):
        """测试使用低置信度阈值"""
        boxes = detector.detect(sample_image, confidence_threshold=0.0)
        # 即使是低阈值，空白图像也应该返回None或空列表
        assert boxes is None or len(boxes) == 0

    def test_draw_boxes(self, detector, sample_image):
        """测试绘制边界框"""
        # 创建假的边界框
        boxes = [[100, 100, 200, 200, 0.9]]

        # 绘制边界框
        result = detector.draw_boxes(sample_image.copy(), boxes)

        # 验证图像被修改
        assert result.shape == sample_image.shape
        assert not np.array_equal(result, sample_image)


class TestFaceDetectorIntegration:
    """集成测试"""

    def test_detector_initialization_time(self):
        """测试检测器初始化时间（性能测试）"""
        import time

        start_time = time.time()
        detector = FaceDetector(use_gpu=False)
        init_time = time.time() - start_time

        # 初始化应该在合理时间内完成（<10秒）
        assert init_time < 10.0
        print(f"\n检测器初始化时间: {init_time:.2f}秒")

    def test_detector_device_info(self):
        """测试检测器设备信息"""
        import torch

        detector_cpu = FaceDetector(use_gpu=False)
        print(f"\nCPU模式设备: {detector_cpu.device}")

        if torch.cuda.is_available():
            detector_gpu = FaceDetector(use_gpu=True)
            print(f"GPU模式设备: {detector_gpu.device}")
            assert detector_gpu.device.startswith('cuda')
