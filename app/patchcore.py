"""PatchCore compacto (Roth et al., CVPR 2022): WideResNet-50 (layer2+layer3),
agregacion local 3x3, coreset greedy y vecino mas cercano. Entrena solo con piezas OK."""
import torch, torch.nn.functional as F, torchvision
from torchvision import transforms as T
from PIL import Image

class PatchCore:
    def __init__(self, size=224, device=None):
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        w = torchvision.models.Wide_ResNet50_2_Weights.IMAGENET1K_V1
        self.m = torchvision.models.wide_resnet50_2(weights=w).eval().to(self.dev)
        self.tf = T.Compose([T.Resize((size, size)), T.ToTensor(),
                             T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
        self.bank, self.thr = None, None

    @torch.no_grad()
    def _feat(self, img):
        m, x = self.m, self.tf(img.convert("RGB"))[None].to(self.dev)
        x = m.maxpool(m.relu(m.bn1(m.conv1(x))))
        l2 = m.layer2(m.layer1(x)); l3 = m.layer3(l2)
        l2, l3 = F.avg_pool2d(l2, 3, 1, 1), F.avg_pool2d(l3, 3, 1, 1)
        l3 = F.interpolate(l3, size=l2.shape[-2:], mode="bilinear", align_corners=False)
        f = torch.cat([l2, l3], 1)
        return f.flatten(2).permute(0, 2, 1)[0], f.shape[-2:]

    @torch.no_grad()
    def _coreset(self, X, n):
        P = (X @ torch.randn(X.shape[1], 128) / 128 ** .5).to(self.dev)
        idx, d = [0], torch.cdist(P, P[:1]).squeeze(1)
        for _ in range(n - 1):
            i = int(d.argmax()); idx.append(i)
            d = torch.minimum(d, torch.cdist(P, P[i:i + 1]).squeeze(1))
        return X[idx]

    @torch.no_grad()
    def score(self, img):
        q, (h, w) = self._feat(img)
        d = torch.cdist(q, self.bank).min(1).values.reshape(h, w)
        amap = F.interpolate(d[None, None], size=img.size[::-1], mode="bilinear")[0, 0]
        return float(d.max()), amap.cpu().numpy()

    def fit(self, train_paths, val_paths, ratio=0.1, margin=1.05):
        if not train_paths:
            raise ValueError("No hay imágenes OK para entrenamiento.")
        if not val_paths:
            raise ValueError("No hay imágenes OK para calibración. Se necesita al menos una.")
        if not 0 < ratio <= 1:
            raise ValueError("ratio debe estar entre 0 y 1.")
        if margin <= 0:
            raise ValueError("margin debe ser mayor que cero.")
        features = []
        for path in train_paths:
            with Image.open(path) as image:
                features.append(self._feat(image)[0].cpu())
        X = torch.cat(features)
        self.bank = self._coreset(X, max(1, int(len(X) * ratio))).to(self.dev)
        calibration_scores = []
        for path in val_paths:
            with Image.open(path) as image:
                calibration_scores.append(self.score(image)[0])
        self.thr = margin * max(calibration_scores)

    def save(self, path): torch.save({"bank": self.bank.cpu(), "thr": self.thr}, path)

    def load(self, path):
        s = torch.load(path, map_location=self.dev, weights_only=True)
        self.bank, self.thr = s["bank"].to(self.dev), float(s["thr"])
        return self
