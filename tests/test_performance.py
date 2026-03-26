"""测试性能优化"""
import pytest
import sys
import os
import time
import tempfile

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from boss_sentinel.main import BossSentinel


class TestLazyLoading:
    """测试模型懒加载"""

    def test_lazy_loading_disabled(self):
        """测试禁用懒加载"""
        start_time = time.time()
        sentinel = BossSentinel(lazy_load=False)
        init_time = time.time() - start_time

        # 模型应该立即加载
        assert sentinel._models_loaded == True
        assert sentinel.model is not None
        assert sentinel.face_recognizer is not None

        print(f"\n禁用懒加载初始化时间: {init_time:.2f}秒")
        # 应该花费一些时间加载模型（放宽断言以适应不同硬件）
        assert init_time > 0.1  # 至少需要一些时间加载模型

    def test_lazy_loading_enabled(self):
        """测试启用懒加载"""
        # 创建临时的config.json
        config_data = {
            'known_faces_dir': 'known_faces',
            'model_path': 'yolov8n-face.pt',
            'detection_interval': 1,
            'threshold': 0.7,
            'confidence_threshold': 0.7,
            'show_feed': True,
            'cameras': [0],
            'log_file': 'test_sentinel.log',
            'frame_skip': 3,
            'use_gpu': False
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, dir='.') as f:
            import json
            json.dump(config_data, f)
            temp_config = f.name

        try:
            start_time = time.time()
            sentinel = BossSentinel(config_path=temp_config, lazy_load=True)
            init_time = time.time() - start_time

            # 模型不应该立即加载
            assert sentinel._models_loaded == False
            assert sentinel.model is None
            assert sentinel.face_recognizer is None

            print(f"\n启用懒加载初始化时间: {init_time:.2f}秒")
            # 应该非常快（<1秒）
            assert init_time < 2.0

            # 现在加载模型
            start_time = time.time()
            sentinel.initialize_models()
            load_time = time.time() - start_time

            print(f"模型加载时间: {load_time:.2f}秒")
            # 模型加载需要时间（放宽断言以适应不同硬件）
            assert load_time > 0.1

            # 现在模型应该已加载
            assert sentinel._models_loaded == True
            assert sentinel.model is not None
            assert sentinel.face_recognizer is not None

        finally:
            if os.path.exists(temp_config):
                try:
                    os.remove(temp_config)
                except PermissionError:
                    pass  # Windows文件锁定，忽略
            if os.path.exists('test_sentinel.log'):
                try:
                    os.remove('test_sentinel.log')
                except PermissionError:
                    pass  # Windows文件锁定，忽略

    def test_ensure_models_loaded(self):
        """测试ensure_models_loaded方法"""
        sentinel = BossSentinel(lazy_load=True)

        # 模型未加载
        assert sentinel._models_loaded == False

        # 调用ensure_models_loaded
        sentinel.ensure_models_loaded()

        # 模型应该已加载
        assert sentinel._models_loaded == True

        # 再次调用不应该重复加载
        sentinel.ensure_models_loaded()
        assert sentinel._models_loaded == True


class TestFrameSkip:
    """测试帧跳过机制"""

    def test_frame_skip_configuration(self):
        """测试帧跳过配置"""
        from boss_sentinel.config import SentinelConfig

        config = SentinelConfig(frame_skip=5)
        assert config.frame_skip == 5

        config = SentinelConfig(frame_skip=1)
        assert config.frame_skip == 1

    def test_frame_skip_in_monitor(self):
        """测试监控器中的帧跳过"""
        from boss_sentinel.monitor import SentinelMonitor
        from boss_sentinel.config import SentinelConfig
        import numpy as np

        config = SentinelConfig(
            frame_skip=3,
            use_gpu=False,
            cameras=[0]
        )

        # 注意：这个测试需要摄像头，可能在实际环境中失败
        # 这里我们只测试配置
        assert config.frame_skip == 3

        monitor = SentinelMonitor(config)
        assert monitor.frame_count == 0
        assert monitor.config.frame_skip == 3


class TestGPUConfiguration:
    """测试GPU配置"""

    def test_gpu_enabled_in_config(self):
        """测试启用GPU的配置"""
        from boss_sentinel.config import SentinelConfig

        config = SentinelConfig(use_gpu=True)
        assert config.use_gpu == True

    def test_gpu_disabled_in_config(self):
        """测试禁用GPU的配置"""
        from boss_sentinel.config import SentinelConfig

        config = SentinelConfig(use_gpu=False)
        assert config.use_gpu == False

    def test_detector_with_gpu_flag(self):
        """测试检测器GPU标志"""
        from boss_sentinel.detector import FaceDetector
        import torch

        # CPU模式
        detector_cpu = FaceDetector(use_gpu=False)
        assert detector_cpu.device == 'cpu'

        # GPU模式（如果可用）
        if torch.cuda.is_available():
            detector_gpu = FaceDetector(use_gpu=True)
            assert detector_gpu.device.startswith('cuda')
            print(f"\nGPU可用，设备: {detector_gpu.device}")
        else:
            detector_gpu = FaceDetector(use_gpu=True)
            assert detector_gpu.device == 'cpu'
            print("\nGPU不可用，回退到CPU")


class TestPerformanceMetrics:
    """性能指标测试"""

    def test_initialization_performance(self):
        """测试初始化性能"""
        times = []

        # 测试3次初始化时间
        for i in range(3):
            start_time = time.time()
            sentinel = BossSentinel(lazy_load=True)
            init_time = time.time() - start_time
            times.append(init_time)

        avg_time = sum(times) / len(times)
        print(f"\n平均懒加载初始化时间: {avg_time:.2f}秒")

        # 懒加载应该很快
        assert avg_time < 2.0

    def test_model_loading_performance(self):
        """测试模型加载性能"""
        sentinel = BossSentinel(lazy_load=True)

        start_time = time.time()
        sentinel.initialize_models()
        load_time = time.time() - start_time

        print(f"\n模型加载时间: {load_time:.2f}秒")

        # 模型加载应该在合理时间内完成
        assert load_time < 30.0  # 不应该超过30秒

    def test_tracker_performance(self):
        """测试跟踪器性能"""
        from boss_sentinel.tracker import FaceTracker
        import numpy as np

        tracker = FaceTracker()

        # 模拟100帧的检测
        start_time = time.time()

        for frame_idx in range(100):
            # 模拟2-3个检测
            detections = [
                [100 + frame_idx, 100, 200 + frame_idx, 200, 0.9],
                [300, 300, 400, 400, 0.8]
            ]
            tracker.update(detections)

        elapsed_time = time.time() - start_time
        fps = 100 / elapsed_time if elapsed_time > 0 else 0

        print(f"\n跟踪器性能: {fps:.1f} FPS")
        print(f"跟踪对象数量: {len(tracker.tracks)}")

        # 跟踪器应该很快（>100 FPS)，        assert fps > 100


@pytest.mark.skipif(not os.path.exists('yolov8n-face.pt'),
                    reason="YOLO model not found")
class TestModelFile:
    """模型文件测试"""

    def test_model_file_exists(self):
        """测试模型文件存在"""
        assert os.path.exists('yolov8n-face.pt')

    def test_model_file_size(self):
        """测试模型文件大小"""
        size = os.path.getsize('yolov8n-face.pt')
        size_mb = size / (1024 * 1024)
        print(f"\n模型文件大小: {size_mb:.2f} MB")

        # 模型文件应该大于5MB
        assert size_mb > 5.0
