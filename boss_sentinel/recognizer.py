import os
import cv2
import numpy as np
import torch
from PIL import Image
from facenet_pytorch import InceptionResnetV1
from typing import Dict, List, Optional, Tuple

class FaceRecognizer:
    """基于FaceNet的人脸识别器"""

    def __init__(self, known_faces_dir: str = "known_faces"):
        """
        初始化人脸识别器

        参数:
            known_faces_dir: 已知人脸图像存储目录
        """
        self.known_faces_dir = known_faces_dir
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval()
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

    def _extract_embedding(self, img_path: str) -> Optional[np.ndarray]:
        """从图像文件提取特征向量"""
        img = Image.open(img_path).convert('RGB').resize((160, 160))
        img_tensor = torch.tensor(np.array(img)).permute(2, 0, 1).float().unsqueeze(0)
        return self.resnet(img_tensor).detach().numpy()
        
    def get_embedding(self, face_img: np.ndarray) -> np.ndarray:
        """
        获取人脸图像的特征向量
        
        参数:
            face_img: 人脸图像(BGR格式)
            
        返回:
            人脸特征向量
        """
        face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)).resize((160, 160))
        face_tensor = torch.tensor(np.array(face_pil)).permute(2, 0, 1).float().unsqueeze(0)
        return self.resnet(face_tensor).detach().numpy()
        
    def compare_faces(self, embedding: np.ndarray, threshold: float = 0.7) -> Tuple[Optional[str], float]:
        """
        与已知人脸比对
        
        参数:
            embedding: 待比对人脸特征向量
            threshold: 相似度阈值
            
        返回:
            (匹配的人名, 最高相似度)
        """
        best_match = None
        best_similarity = 0.0
        
        for name, known_embedding in self.known_embeddings.items():
            similarity = np.dot(embedding, known_embedding.T) / (
                np.linalg.norm(embedding) * np.linalg.norm(known_embedding))
                
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = name if similarity > threshold else None
                
        return best_match, best_similarity