import logging
import math
import os
import cv2
import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from facenet_pytorch import InceptionResnetV1
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Minimum face dimension (pixels) for a face crop to be considered valid
_MIN_FACE_SIZE = 30


class FaceRecognizer:
    """基于FaceNet的人脸识别器"""

    def __init__(self, known_faces_dir: str = "known_faces", device: str = "cpu"):
        """
        初始化人脸识别器

        参数:
            known_faces_dir: 已知人脸图像存储目录
            device: 计算设备 ('cpu' 或 'cuda')
        """
        self.known_faces_dir = known_faces_dir
        self.device = device
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        self.known_embeddings: Dict[str, np.ndarray] = {}
        self._load_known_faces()

    def _load_known_faces(self) -> None:
        """
        加载已知人脸特征向量

        支持两种目录结构:
        1. 多人物子目录: known_faces/person_name/*.jpg
        2. 单层目录: known_faces/person_name.jpg (文件名即人名)
        """
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir, exist_ok=True)
            return

        # 遍历目录
        for entry in os.scandir(self.known_faces_dir):
            if entry.is_dir():
                # 子目录模式: 每个子目录是一个人
                self._load_person_directory(entry.name, entry.path)
            elif entry.is_file() and entry.name.lower().endswith(('.png', '.jpg', '.jpeg')):
                # 单文件模式: 文件名是人名
                person_name = os.path.splitext(entry.name)[0]
                self._load_single_image(person_name, entry.path)

        print(f"已加载 {len(self.known_embeddings)} 个人物特征")

    def _load_person_directory(self, person_name: str, dir_path: str) -> None:
        """加载一个人的多张照片（子目录模式）"""
        embeddings = []

        for img_file in os.scandir(dir_path):
            if img_file.is_file() and img_file.name.lower().endswith(('.png', '.jpg', '.jpeg')):
                try:
                    embedding = self._extract_embedding(img_file.path)
                    if embedding is not None:
                        embeddings.append(embedding)
                        print(f"  加载 {person_name}/{img_file.name}")
                except Exception as e:
                    print(f"  警告: 加载 {img_file.path} 失败: {e}")

        if embeddings:
            # 使用平均特征向量
            self.known_embeddings[person_name] = np.mean(embeddings, axis=0)
            print(f"已加载 {person_name} 的 {len(embeddings)} 张照片特征")

    def _load_single_image(self, person_name: str, img_path: str) -> None:
        """加载单张照片"""
        try:
            embedding = self._extract_embedding(img_path)
            if embedding is not None:
                self.known_embeddings[person_name] = embedding
                print(f"已加载 {person_name} 的照片特征")
        except Exception as e:
            print(f"加载图像 {img_path} 失败: {e}")

    @staticmethod
    def _align_face(face_img: np.ndarray, keypoints: Optional[Dict[str, Tuple[int, int]]] = None) -> np.ndarray:
        """
        根据关键点对人脸进行对齐，使双眼水平。

        参数:
            face_img: BGR 格式的人脸图像
            keypoints: 可选关键点字典，需包含 'left_eye' 和 'right_eye' 坐标

        返回:
            对齐后的 BGR 人脸图像
        """
        if keypoints is None:
            return face_img
        left_eye = keypoints.get('left_eye')
        right_eye = keypoints.get('right_eye')
        if left_eye is None or right_eye is None:
            return face_img

        (lx, ly), (rx, ry) = left_eye, right_eye
        angle = math.degrees(math.atan2(ry - ly, rx - lx))
        if abs(angle) < 0.5:
            return face_img

        h, w = face_img.shape[:2]
        center = (w / 2.0, h / 2.0)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        cos_val = abs(rotation_matrix[0, 0])
        sin_val = abs(rotation_matrix[0, 1])
        new_w = int(h * sin_val + w * cos_val)
        new_h = int(h * cos_val + w * sin_val)
        rotation_matrix[0, 2] += (new_w - w) / 2.0
        rotation_matrix[1, 2] += (new_h - h) / 2.0
        aligned = cv2.warpAffine(face_img, rotation_matrix, (new_w, new_h), flags=cv2.INTER_LINEAR)
        return aligned

    def _extract_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """
        从图像文件提取特征向量。

        包含 PIL 打开异常保护、归一化至 [0,1]、以及最小人脸质量检查。

        参数:
            img_path: 图像文件路径

        返回:
            512 维特征向量，若图像无效则返回 None
        """
        try:
            img = Image.open(img_path).convert('RGB')
        except (UnidentifiedImageError, OSError) as exc:
            logger.warning("无法打开图像 %s: %s", img_path, exc)
            return None

        img_array = np.array(img)
        h, w = img_array.shape[:2]
        if h < _MIN_FACE_SIZE or w < _MIN_FACE_SIZE:
            logger.warning("图像 %s 尺寸 %dx%d 小于最小要求 %dx%d，已跳过",
                           img_path, w, h, _MIN_FACE_SIZE, _MIN_FACE_SIZE)
            return None

        img_resized = img.resize((160, 160))
        img_tensor = torch.tensor(np.array(img_resized)).permute(2, 0, 1).float().unsqueeze(0)
        img_tensor = img_tensor / 255.0
        img_tensor = img_tensor.to(self.device)
        return self.resnet(img_tensor).detach().cpu().numpy().flatten()

    def get_embedding(self, face_img: np.ndarray,
                      keypoints: Optional[Dict[str, Tuple[int, int]]] = None) -> Optional[np.ndarray]:
        """
        获取人脸图像的特征向量

        参数:
            face_img: 人脸图像(BGR格式)
            keypoints: 可选关键点字典，用于人脸对齐

        返回:
            人脸特征向量，若图像太小则返回 None
        """
        h, w = face_img.shape[:2]
        if h < _MIN_FACE_SIZE or w < _MIN_FACE_SIZE:
            logger.debug("人脸图像 %dx%d 小于最小要求 %dx%d", w, h, _MIN_FACE_SIZE, _MIN_FACE_SIZE)
            return None

        if keypoints is not None:
            face_img = self._align_face(face_img, keypoints)

        face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)).resize((160, 160))
        face_tensor = torch.tensor(np.array(face_pil)).permute(2, 0, 1).float().unsqueeze(0)
        face_tensor = face_tensor / 255.0
        face_tensor = face_tensor.to(self.device)
        return self.resnet(face_tensor).detach().cpu().numpy().flatten()

    def batch_get_embeddings(self, face_images: List[np.ndarray]) -> List[Optional[np.ndarray]]:
        """
        批量提取多张人脸图像的特征向量（单次前向推理）。

        参数:
            face_images: BGR 格式人脸图像列表

        返回:
            与输入等长的列表，无效人脸对应位置为 None
        """
        if not face_images:
            return []

        tensors: List[torch.Tensor] = []
        valid_indices: List[int] = []
        results: List[Optional[np.ndarray]] = [None] * len(face_images)

        for idx, face_img in enumerate(face_images):
            h, w = face_img.shape[:2]
            if h < _MIN_FACE_SIZE or w < _MIN_FACE_SIZE:
                continue
            face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)).resize((160, 160))
            t = torch.tensor(np.array(face_pil)).permute(2, 0, 1).float()
            tensors.append(t)
            valid_indices.append(idx)

        if not tensors:
            return results

        batch = torch.stack(tensors, dim=0) / 255.0
        batch = batch.to(self.device)
        with torch.no_grad():
            embeddings = self.resnet(batch).detach().cpu().numpy()

        for i, orig_idx in enumerate(valid_indices):
            results[orig_idx] = embeddings[i].flatten()

        return results

    def compare_faces(self, embedding: np.ndarray, threshold: float = 0.7) -> Tuple[Optional[str], float]:
        """
        与已知人脸比对（向量化实现，单次矩阵乘法）

        参数:
            embedding: 待比对人脸特征向量
            threshold: 相似度阈值

        返回:
            (匹配的人名, 最高相似度)
        """
        if not self.known_embeddings:
            return None, 0.0

        names = list(self.known_embeddings.keys())
        known_matrix = np.stack([self.known_embeddings[n] for n in names])  # (N, 512)

        # 向量化余弦相似度
        embedding_norm = np.linalg.norm(embedding)
        known_norms = np.linalg.norm(known_matrix, axis=1)
        similarities = np.dot(known_matrix, embedding) / (known_norms * embedding_norm + 1e-10)

        best_idx = int(np.argmax(similarities))
        best_similarity = float(similarities[best_idx])
        best_match = names[best_idx] if best_similarity > threshold else None

        return best_match, best_similarity

    def reload_faces(self, known_faces_dir: str) -> None:
        """
        重新扫描人脸目录并更新特征向量，不重新初始化模型。

        参数:
            known_faces_dir: 已知人脸图像存储目录
        """
        self.known_faces_dir = known_faces_dir
        self.known_embeddings.clear()
        self._load_known_faces()
        logger.info("已重新加载人脸目录: %s (%d 个人物)", known_faces_dir, len(self.known_embeddings))

    def cleanup(self) -> None:
        """释放模型引用以回收 GPU 显存。"""
        if hasattr(self, 'resnet') and self.resnet is not None:
            del self.resnet
            self.resnet = None
        if self.device == 'cuda' and torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("FaceRecognizer 资源已释放")