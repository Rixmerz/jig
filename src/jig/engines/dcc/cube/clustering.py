"""
Semantic Clustering for DeltaCodeCube.

Automatically groups similar files using K-means clustering
on the 86D feature vectors. No external ML APIs required.

Features:
1. Automatic cluster discovery
2. Cluster naming based on dominant characteristics
3. Outlier detection (files that don't fit well)
4. Cluster quality metrics (silhouette score)
5. Suggestions for misclassified files
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Cluster:
    """A cluster of similar files."""
    id: int
    name: str
    centroid: np.ndarray
    files: list[dict[str, Any]]
    size: int
    avg_distance: float
    dominant_domain: str
    characteristics: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "avg_distance": round(self.avg_distance, 4),
            "dominant_domain": self.dominant_domain,
            "characteristics": self.characteristics,
            "files": self.files,
        }


@dataclass
class ClusteringResult:
    """Results of clustering analysis."""
    clusters: list[Cluster]
    outliers: list[dict[str, Any]]
    silhouette_score: float
    total_files: int
    optimal_k: int
    misclassified: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_files": self.total_files,
            "num_clusters": len(self.clusters),
            "optimal_k": self.optimal_k,
            "silhouette_score": round(self.silhouette_score, 4),
            "outliers_count": len(self.outliers),
            "misclassified_count": len(self.misclassified),
            "clusters": [c.to_dict() for c in self.clusters],
            "outliers": self.outliers,
            "misclassified": self.misclassified,
        }


class SemanticClustering:
    """
    Clusters files based on their feature vectors.

    Uses K-means with automatic K selection via elbow method.
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.file_data: list[dict[str, Any]] = []
        self.feature_matrix: np.ndarray | None = None
        self.labels: np.ndarray | None = None
        self.centroids: np.ndarray | None = None

    def load_data(self) -> int:
        """
        Load all code points from database.

        Returns:
            Number of files loaded.
        """
        cursor = self.conn.execute("""
            SELECT id, file_path, lexical_features, structural_features,
                   semantic_features, line_count
            FROM code_points
        """)

        self.file_data = []
        features_list = []

        for row in cursor.fetchall():
            lexical = np.array(json.loads(row["lexical_features"]), dtype=np.float64)
            structural = np.array(json.loads(row["structural_features"]), dtype=np.float64)
            semantic = np.array(json.loads(row["semantic_features"]), dtype=np.float64)

            # Concatenate all features
            full_features = np.concatenate([lexical, structural, semantic])
            features_list.append(full_features)

            # Get domain from semantic features
            domains = ["auth", "db", "api", "ui", "util"]
            domain_idx = np.argmax(semantic[:len(domains)]) if len(semantic) >= len(domains) else 0
            domain = domains[domain_idx] if domain_idx < len(domains) else "unknown"

            self.file_data.append({
                "id": row["id"],
                "file_path": row["file_path"],
                "name": Path(row["file_path"]).name,
                "domain": domain,
                "line_count": row["line_count"],
            })

        if features_list:
            # Normalize feature vectors to same dimension (pad shorter ones with zeros)
            max_dim = max(len(f) for f in features_list)
            normalized_features = []
            for f in features_list:
                if len(f) < max_dim:
                    f = np.pad(f, (0, max_dim - len(f)), mode='constant', constant_values=0)
                normalized_features.append(f)
            self.feature_matrix = np.vstack(normalized_features)

        return len(self.file_data)

    def cluster(self, k: int | None = None, max_k: int = 10) -> ClusteringResult:
        """
        Perform clustering on the files.

        Args:
            k: Number of clusters. If None, finds optimal K.
            max_k: Maximum K to try when finding optimal.

        Returns:
            ClusteringResult with clusters and metrics.
        """
        if self.feature_matrix is None or len(self.file_data) == 0:
            self.load_data()

        if self.feature_matrix is None or len(self.file_data) < 3:
            return ClusteringResult(
                clusters=[],
                outliers=[],
                silhouette_score=0,
                total_files=len(self.file_data),
                optimal_k=0,
                misclassified=[],
            )

        n_samples = len(self.file_data)
        max_k = min(max_k, n_samples - 1)

        # Find optimal K if not provided
        if k is None:
            k = self._find_optimal_k(max_k)

        # Ensure k is valid
        k = max(2, min(k, n_samples - 1))

        # Run K-means
        self.labels, self.centroids = self._kmeans(k)

        # Build clusters
        clusters = self._build_clusters(k)

        # Find outliers (files far from their centroid)
        outliers = self._find_outliers()

        # Find potentially misclassified files
        misclassified = self._find_misclassified()

        # Calculate silhouette score
        silhouette = self._silhouette_score()

        return ClusteringResult(
            clusters=clusters,
            outliers=outliers,
            silhouette_score=silhouette,
            total_files=n_samples,
            optimal_k=k,
            misclassified=misclassified,
        )

    def _kmeans(
        self,
        k: int,
        max_iterations: int = 100,
        tolerance: float = 1e-4,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        K-means clustering implementation.

        Args:
            k: Number of clusters.
            max_iterations: Maximum iterations.
            tolerance: Convergence tolerance.

        Returns:
            Tuple of (labels, centroids).
        """
        n_samples = self.feature_matrix.shape[0]

        # Initialize centroids using K-means++
        centroids = self._kmeans_plusplus_init(k)

        labels = np.zeros(n_samples, dtype=int)

        for iteration in range(max_iterations):
            # Assign labels
            for i in range(n_samples):
                distances = np.linalg.norm(self.feature_matrix[i] - centroids, axis=1)
                labels[i] = np.argmin(distances)

            # Update centroids
            new_centroids = np.zeros_like(centroids)
            for j in range(k):
                cluster_points = self.feature_matrix[labels == j]
                if len(cluster_points) > 0:
                    new_centroids[j] = cluster_points.mean(axis=0)
                else:
                    # Empty cluster - reinitialize
                    new_centroids[j] = self.feature_matrix[np.random.randint(n_samples)]

            # Check convergence
            diff = np.linalg.norm(new_centroids - centroids)
            centroids = new_centroids

            if diff < tolerance:
                logger.debug(f"K-means converged in {iteration + 1} iterations")
                break

        return labels, centroids

    def _kmeans_plusplus_init(self, k: int) -> np.ndarray:
        """Initialize centroids using K-means++ algorithm."""
        n_samples = self.feature_matrix.shape[0]
        centroids = []

        # First centroid: random
        idx = np.random.randint(n_samples)
        centroids.append(self.feature_matrix[idx].copy())

        # Remaining centroids: weighted by distance
        for _ in range(1, k):
            distances = np.zeros(n_samples)
            for i in range(n_samples):
                min_dist = min(np.linalg.norm(self.feature_matrix[i] - c) for c in centroids)
                distances[i] = min_dist ** 2

            # Normalize to probabilities
            probs = distances / distances.sum()
            idx = np.random.choice(n_samples, p=probs)
            centroids.append(self.feature_matrix[idx].copy())

        return np.vstack(centroids)

    def _find_optimal_k(self, max_k: int) -> int:
        """Find optimal K using elbow method."""
        if max_k < 2:
            return 2

        inertias = []
        k_range = range(2, max_k + 1)

        for k in k_range:
            labels, centroids = self._kmeans(k, max_iterations=50)

            # Calculate inertia (sum of squared distances to centroids)
            inertia = 0
            for i, label in enumerate(labels):
                inertia += np.linalg.norm(self.feature_matrix[i] - centroids[label]) ** 2
            inertias.append(inertia)

        # Find elbow using second derivative
        if len(inertias) < 3:
            return 2

        # Calculate rate of change
        diffs = np.diff(inertias)
        diffs2 = np.diff(diffs)

        # Elbow is where second derivative is maximum (most negative acceleration)
        elbow_idx = np.argmax(np.abs(diffs2)) + 2  # +2 because we start at k=2

        return min(elbow_idx, max_k)

    def _build_clusters(self, k: int) -> list[Cluster]:
        """Build cluster objects from labels."""
        clusters = []

        for cluster_id in range(k):
            mask = self.labels == cluster_id
            cluster_files = [self.file_data[i] for i in range(len(self.file_data)) if mask[i]]

            if not cluster_files:
                continue

            # Calculate average distance to centroid
            cluster_features = self.feature_matrix[mask]
            distances = np.linalg.norm(cluster_features - self.centroids[cluster_id], axis=1)
            avg_distance = float(distances.mean())

            # Find dominant domain
            domain_counts: dict[str, int] = {}
            for f in cluster_files:
                domain_counts[f["domain"]] = domain_counts.get(f["domain"], 0) + 1
            dominant_domain = max(domain_counts, key=domain_counts.get) if domain_counts else "unknown"

            # Generate cluster name and characteristics
            name, characteristics = self._analyze_cluster(cluster_files, self.centroids[cluster_id])

            clusters.append(Cluster(
                id=cluster_id,
                name=name,
                centroid=self.centroids[cluster_id],
                files=[{"name": f["name"], "path": f["file_path"], "domain": f["domain"]}
                       for f in cluster_files],
                size=len(cluster_files),
                avg_distance=avg_distance,
                dominant_domain=dominant_domain,
                characteristics=characteristics,
            ))

        return clusters

    def _analyze_cluster(self, files: list[dict], centroid: np.ndarray) -> tuple[str, list[str]]:
        """Analyze cluster to generate name and characteristics."""
        # Count domains
        domain_counts: dict[str, int] = {}
        for f in files:
            domain_counts[f["domain"]] = domain_counts.get(f["domain"], 0) + 1

        dominant = max(domain_counts, key=domain_counts.get) if domain_counts else "mixed"
        total = len(files)
        dominant_pct = domain_counts.get(dominant, 0) / total if total > 0 else 0

        characteristics = []

        # Name based on composition
        if dominant_pct > 0.7:
            name = f"{dominant.upper()} Cluster"
            characteristics.append(f"{dominant_pct:.0%} {dominant} files")
        elif len(domain_counts) <= 2:
            domains = list(domain_counts.keys())
            name = f"{domains[0]}/{domains[1] if len(domains) > 1 else ''} Mixed"
            characteristics.append(f"Mixed: {', '.join(f'{d}({c})' for d, c in domain_counts.items())}")
        else:
            name = "General Cluster"
            characteristics.append("Diverse file types")

        # Analyze centroid for structural characteristics
        # Structural features are at indices 65-80 in 86D space
        structural_start = 65
        if len(centroid) > structural_start + 5:
            complexity = centroid[structural_start + 6]  # cyclomatic
            if complexity > 0.5:
                characteristics.append("High complexity files")
            elif complexity < 0.2:
                characteristics.append("Simple/utility files")

        return name, characteristics

    def _find_outliers(self, threshold_factor: float = 2.0) -> list[dict[str, Any]]:
        """Find files that are far from their cluster centroid."""
        outliers = []

        for cluster_id in range(len(self.centroids)):
            mask = self.labels == cluster_id
            if not mask.any():
                continue

            cluster_features = self.feature_matrix[mask]
            distances = np.linalg.norm(cluster_features - self.centroids[cluster_id], axis=1)

            mean_dist = distances.mean()
            std_dist = distances.std()
            threshold = mean_dist + threshold_factor * std_dist

            cluster_indices = np.where(mask)[0]
            for i, dist in enumerate(distances):
                if dist > threshold:
                    file_idx = cluster_indices[i]
                    outliers.append({
                        "name": self.file_data[file_idx]["name"],
                        "path": self.file_data[file_idx]["file_path"],
                        "cluster_id": cluster_id,
                        "distance": float(dist),
                        "threshold": float(threshold),
                    })

        return outliers

    def _find_misclassified(self) -> list[dict[str, Any]]:
        """
        Find files that might be better in a different cluster.

        A file is potentially misclassified if:
        - Its distance to its centroid is high
        - It's closer to another cluster's centroid
        """
        misclassified = []

        for i, file_data in enumerate(self.file_data):
            current_cluster = self.labels[i]
            current_dist = np.linalg.norm(self.feature_matrix[i] - self.centroids[current_cluster])

            # Check distance to other centroids
            for other_cluster in range(len(self.centroids)):
                if other_cluster == current_cluster:
                    continue

                other_dist = np.linalg.norm(self.feature_matrix[i] - self.centroids[other_cluster])

                # If significantly closer to another cluster
                if other_dist < current_dist * 0.8:
                    misclassified.append({
                        "name": file_data["name"],
                        "path": file_data["file_path"],
                        "current_cluster": current_cluster,
                        "suggested_cluster": other_cluster,
                        "current_distance": float(current_dist),
                        "suggested_distance": float(other_dist),
                        "improvement": f"{(1 - other_dist/current_dist)*100:.0f}% closer",
                    })
                    break

        return misclassified

    def _silhouette_score(self) -> float:
        """Calculate silhouette score for clustering quality."""
        if self.labels is None or len(set(self.labels)) < 2:
            return 0.0

        n_samples = len(self.file_data)
        silhouette_vals = np.zeros(n_samples)

        for i in range(n_samples):
            cluster_i = self.labels[i]

            # a(i) = average distance to points in same cluster
            same_cluster = self.feature_matrix[self.labels == cluster_i]
            if len(same_cluster) > 1:
                a_i = np.mean([np.linalg.norm(self.feature_matrix[i] - x) for x in same_cluster])
            else:
                a_i = 0

            # b(i) = minimum average distance to points in other clusters
            b_i = float('inf')
            for other_cluster in set(self.labels):
                if other_cluster == cluster_i:
                    continue
                other_points = self.feature_matrix[self.labels == other_cluster]
                if len(other_points) > 0:
                    avg_dist = np.mean([np.linalg.norm(self.feature_matrix[i] - x) for x in other_points])
                    b_i = min(b_i, avg_dist)

            if b_i == float('inf'):
                b_i = 0

            # Silhouette value
            if max(a_i, b_i) > 0:
                silhouette_vals[i] = (b_i - a_i) / max(a_i, b_i)

        return float(np.mean(silhouette_vals))


def cluster_codebase(conn: sqlite3.Connection, k: int | None = None) -> dict[str, Any]:
    """
    Convenience function to cluster the codebase.

    Args:
        conn: Database connection.
        k: Number of clusters (None for automatic).

    Returns:
        Clustering results as dictionary.
    """
    clustering = SemanticClustering(conn)
    clustering.load_data()
    result = clustering.cluster(k=k)
    return result.to_dict()
