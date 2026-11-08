"""Synthetic metric depth + API contract checks. No claims about real iPhone sensing."""
import base64
import json
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.arkit_depth import ARKitDepthVision, ARKitPacket, parse_packet, unproject_world
from backend.device import MockDevice
from tests.conftest import KEY


def make_packet(obstacle=None, floor=True, confidence=2, tracking="normal"):
    """Render exact pinhole-camera depth to floor + optional vertical obstacle."""
    dw, dh, iw, ih = 80, 60, 640, 480
    fx, fy, cx, cy = 550., 550., 320., 240.
    theta = np.deg2rad(-35)
    rot = np.array([[1, 0, 0], [0, np.cos(theta), -np.sin(theta)],
                    [0, np.sin(theta), np.cos(theta)]])
    pose = np.eye(4)
    pose[:3, :3] = rot
    pose[:3, 3] = [0, 1.15, 0]
    depths = []
    for j in range(dh):
        for i in range(dw):
            pixel_x = (i + 0.5) * iw / dw
            pixel_y = (j + 0.5) * ih / dh
            ray = rot @ np.array([(pixel_x-cx)/fx, -(pixel_y-cy)/fy, -1])
            floor_d = -1.15 / ray[1] if ray[1] < -0.001 else 0
            d = floor_d if 0.2 < floor_d < 5 else 0
            if obstacle and ray[2] < 0:
                obstacle_d = -1.15 / ray[2]
                point = np.array([0, 1.15, 0]) + ray * obstacle_d
                xmin, xmax = obstacle
                if xmin <= point[0] <= xmax and 0.15 < point[1] < 1.4 and obstacle_d < d:
                    d = obstacle_d
            depths.append(round(float(d), 5))
    buffer = BytesIO()
    Image.fromarray(np.full((ih, iw, 3), 130, np.uint8)).save(buffer, 'JPEG')
    return dict(
        jpeg_b64=base64.b64encode(buffer.getvalue()).decode(),
        image_width=iw, image_height=ih, depth_width=dw, depth_height=dh,
        depth_m=depths, confidence=[confidence]*len(depths),
        intrinsics=[fx, fy, cx, cy], camera_to_world=pose.flatten(order='F').tolist(),
        floor_y_world=0.0 if floor else None, tracking=tracking,
    )


@pytest.mark.parametrize(('obstacle','expected'), [
    (None, 'center'),
    ((-1.15, -0.45), 'center'),
    ((0.45, 1.15), 'center'),
    ((-0.3, 0.3), 'unknown'),
])
def test_measured_depth_decisions(obstacle, expected):
    packet = ARKitPacket.model_validate(make_packet(obstacle))
    decision = ARKitDepthVision().predict(packet)
    assert decision.direction == expected
    assert decision.source == 'arkit_lidar'
    assert decision.scene['depth_kind'] == 'metric_lidar_depth_m'
    assert decision.scene['corridor_bands']['center']


def test_floor_anchor_optional_but_tracking_and_depth_still_required():
    clear = make_packet(floor=False)
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(clear))
    assert result.direction == 'center'
    assert result.scene['floor_required'] is False
    for changes in ({'tracking': 'limited'}, {'confidence': [0]*4800}):
        packet = make_packet(floor=False)
        packet.update(changes)
        assert ARKitDepthVision().predict(ARKitPacket.model_validate(packet)).direction == 'unknown'
    # An inconsistent floor anchor should NOT turn off measured depth sensing.
    packet = make_packet()
    packet['floor_y_world'] = 10.0
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(packet))
    assert result.direction == 'center'
    assert 'floor_anchor_warning' in result.scene


def test_wrong_orientation_and_untrusted_shapes():
    pkt = make_packet()
    pkt['image_width'] = 480
    pkt['image_height'] = 640
    assert ARKitDepthVision().predict(ARKitPacket.model_validate(pkt)).direction == 'unknown'
    pkt = make_packet()
    pkt['depth_m'].pop()
    with pytest.raises(ValueError):
        parse_packet(json.dumps(pkt).encode())
    pkt = make_packet()
    pkt['camera_to_world'] = [0]*16
    with pytest.raises(ValueError):
        parse_packet(json.dumps(pkt).encode())


def test_native_endpoint_requires_auth_and_obstacle_mode(settings):
    data = json.dumps(make_packet()).encode()
    device = MockDevice()
    with TestClient(create_app(settings, device=device)) as c:
        url = '/api/arkit/frame?generation=1&sequence=0'
        assert c.post(url, content=data, headers={'content-type':'application/json'}).status_code == 401
        h = {'X-API-Key':KEY, 'content-type':'application/json'}
        assert c.post(url, content=data, headers=h).status_code == 409
        manual = c.post('/api/arm', json={'mode':'manual'}, headers=h).json()
        assert c.post(f'/api/arkit/frame?generation={manual["generation"]}&sequence=0',
                      content=data, headers=h).status_code == 409
        state = c.post('/api/arm', json={'mode':'obstacle'}, headers=h).json()
        gen = state['generation']
        for i in range(3):
            r = c.post(f'/api/arkit/frame?generation={gen}&sequence={i}',
                       content=data, headers=h)
            assert r.status_code == 200, r.text
        assert r.json()['sensor'] == 'arkit_lidar'
        assert r.json()['direction'] == 'center'
        assert r.json()['commanded_angle'] == 90
        assert c.post(f'/api/arkit/frame?generation={gen}&sequence=1',
                      content=data, headers=h).status_code == 409
        c.post('/api/stop', headers=h)
        assert c.post(f'/api/arkit/frame?generation={gen}&sequence=4',
                      content=data, headers=h).status_code == 409


def test_ar_endpoint_fail_closed_on_uncertainty(settings):
    pkt = make_packet(floor=False)
    pkt['depth_m'] = [0.0] * len(pkt['depth_m'])
    data = json.dumps(pkt).encode()
    with TestClient(create_app(settings, device=MockDevice())) as c:
        headers = {'X-API-Key':KEY, 'content-type':'application/json'}
        gen = c.post('/api/arm', json={'mode':'obstacle'}, headers=headers).json()['generation']
        r = c.post(f'/api/arkit/frame?generation={gen}&sequence=0', content=data, headers=headers)
        assert r.status_code == 200
        assert r.json()['commanded_angle'] == 90
        assert r.json()['vision']['reason'] == 'Insufficient reliable LiDAR returns'

def test_depth_reprojection_matches_floor_plane():
    pkt = ARKitPacket.model_validate(make_packet())
    _, _, height, good, camera_height = unproject_world(pkt)
    assert camera_height == pytest.approx(1.15)
    assert (np.abs(height)[good] < 0.01).mean() > 0.99


def test_optional_semantic_floor_path_and_invalid_mask():
    from backend.obstacles import ObstacleVision
    im = np.full((240, 320, 3), 120, np.uint8)
    inverse = np.broadcast_to(np.linspace(0.0, 1.0, 240)[:, None], (240, 320)).copy()
    mask = np.zeros((240, 320), dtype=bool)
    mask[90:] = True
    detector = ObstacleVision()
    result = detector.analyze(im, [], inverse, semantic_mask=mask)
    assert result.scene["floor_estimator"] == "segformer_ade20k_floor_class"
    bad = detector.analyze(im, [], inverse, semantic_mask=np.zeros((20, 20)))
    assert bad.direction == "unknown"
    assert bad.reason == "Invalid semantic floor mask"
