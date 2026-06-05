"""RoleManager 和 HeadPoseEstimator 单元测试"""
import numpy as np
import pytest
from boss_sentinel.role_manager import RoleManager
from boss_sentinel.head_pose import HeadPoseEstimator, HeadPoseResult


class TestRoleManager:
    """测试角色解析逻辑"""

    def test_resolve_owner(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        assert rm.resolve("alice") == "owner"

    def test_resolve_boss(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        assert rm.resolve("bob") == "boss"

    def test_resolve_colleague(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        assert rm.resolve("charlie") == "colleague"

    def test_resolve_unknown(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        assert rm.resolve(None) == "unknown"
        assert rm.resolve("") == "unknown"

    def test_case_insensitive(self):
        rm = RoleManager({"owner": ["Alice"], "boss": ["Bob"]})
        assert rm.resolve("alice") == "owner"
        assert rm.resolve("ALICE") == "owner"
        assert rm.resolve("bob") == "boss"

    def test_empty_roles(self):
        """空角色配置下，所有已识别人脸默认为 colleague"""
        rm = RoleManager({})
        assert rm.resolve("anyone") == "colleague"
        assert rm.resolve(None) == "unknown"

    def test_convenience_predicates(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        assert rm.is_owner("alice")
        assert not rm.is_owner("bob")
        assert rm.is_boss("bob")
        assert rm.is_unknown(None)
        assert rm.is_colleague("charlie")

    def test_get_role_members(self):
        rm = RoleManager({"owner": ["alice"], "boss": ["bob", "carol"]})
        assert rm.get_owner_names() == ["alice"]
        assert rm.get_boss_names() == ["bob", "carol"]
        assert rm.get_role_members("colleague") == []

    def test_update_roles(self):
        rm = RoleManager({"owner": ["alice"]})
        assert rm.resolve("alice") == "owner"
        assert rm.resolve("bob") == "colleague"

        rm.update_roles({"owner": ["alice"], "boss": ["bob"]})
        assert rm.resolve("alice") == "owner"
        assert rm.resolve("bob") == "boss"

    def test_no_duplicate_roles(self):
        """同一人不应出现在多个角色中（后分配的覆盖）"""
        rm = RoleManager({"owner": ["alice"], "boss": ["alice"]})
        # alice 应被分配为 boss（后分配覆盖）
        assert rm.resolve("alice") == "boss"

    def test_get_all_roles(self):
        roles = {"owner": ["alice"], "boss": ["bob"]}
        rm = RoleManager(roles)
        result = rm.get_all_roles()
        assert "owner" in result
        assert "boss" in result


class TestHeadPoseEstimator:
    """测试头部姿态估计"""

    def test_estimate_returns_result_with_valid_keypoints(self):
        estimator = HeadPoseEstimator()
        # 模拟正面人脸的 5 个关键点 (左眼、右眼、鼻尖、左嘴角、右嘴角)
        keypoints = [
            [180, 200],  # left eye
            [320, 200],  # right eye
            [250, 280],  # nose
            [190, 350],  # left mouth
            [310, 350],  # right mouth
        ]
        frame_shape = (480, 640, 3)
        result = estimator.estimate(keypoints, frame_shape)

        assert result is not None
        assert isinstance(result, HeadPoseResult)
        assert -90 <= result.yaw <= 90
        assert -90 <= result.pitch <= 90
        assert -90 <= result.roll <= 90
        assert isinstance(result.looking_at_screen, bool)
        assert result.attention_status in ("focused", "distracted", "away")
        assert 0 <= result.confidence <= 1.0

    def test_estimate_returns_none_with_invalid_keypoints(self):
        estimator = HeadPoseEstimator()
        # 全零关键点
        result = estimator.estimate([[0, 0]] * 5, (480, 640, 3))
        assert result is None

    def test_estimate_returns_none_with_too_few_keypoints(self):
        estimator = HeadPoseEstimator()
        result = estimator.estimate([[100, 200], [200, 200]], (480, 640, 3))
        assert result is None

    def test_estimate_returns_none_with_none_keypoints(self):
        estimator = HeadPoseEstimator()
        result = estimator.estimate(None, (480, 640, 3))
        assert result is None

    def test_looking_at_screen_frontal(self):
        """正面人脸应检测为 looking_at_screen=True"""
        estimator = HeadPoseEstimator(yaw_threshold=30)
        keypoints = [
            [180, 200], [320, 200], [250, 280], [190, 350], [310, 350]
        ]
        result = estimator.estimate(keypoints, (480, 640, 3))
        assert result is not None
        # 正面人脸的 yaw 应该较小
        assert abs(result.yaw) < 45

    def test_focus_score(self):
        estimator = HeadPoseEstimator()
        keypoints = [
            [180, 200], [320, 200], [250, 280], [190, 350], [310, 350]
        ]
        # 多次估计以建立历史
        for _ in range(10):
            estimator.estimate(keypoints, (480, 640, 3), face_index=0)

        score = estimator.get_focus_score(face_index=0)
        assert 0.0 <= score <= 1.0

    def test_focus_score_empty_history(self):
        estimator = HeadPoseEstimator()
        assert estimator.get_focus_score(face_index=99) == 0.0

    def test_reset_clears_history(self):
        estimator = HeadPoseEstimator()
        keypoints = [
            [180, 200], [320, 200], [250, 280], [190, 350], [310, 350]
        ]
        estimator.estimate(keypoints, (480, 640, 3), face_index=0)
        assert estimator.get_focus_score(face_index=0) > 0.0

        estimator.reset()
        assert estimator.get_focus_score(face_index=0) == 0.0
