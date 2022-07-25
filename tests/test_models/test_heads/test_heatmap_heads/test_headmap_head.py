# Copyright (c) OpenMMLab. All rights reserved.
from typing import List, Tuple
from unittest import TestCase

import numpy as np
import torch
from torch import nn

from mmpose.core.data_structures.pose_data_sample import PoseDataSample
from mmpose.models.heads import HeatmapHead
from mmpose.testing import get_packed_inputs


class TestHeatmapHead(TestCase):

    def _get_feats(self,
                   batch_size: int = 2,
                   feat_shapes: List[Tuple[int, int, int]] = [(32, 6, 8)]):

        feats = [
            torch.rand((batch_size, ) + shape, dtype=torch.float32)
            for shape in feat_shapes
        ]
        return feats

    def _get_data_samples(self, batch_size: int = 2):
        batch_data_samples = [
            inputs['data_sample'] for inputs in get_packed_inputs(batch_size)
        ]
        return batch_data_samples

    def test_init(self):
        # w/o deconv
        head = HeatmapHead(
            in_channels=32, out_channels=17, deconv_out_channels=None)
        self.assertTrue(isinstance(head.deconv_layers, nn.Identity))

        # w/ deconv and w/o conv
        head = HeatmapHead(
            in_channels=32,
            out_channels=17,
            deconv_out_channels=(32, 32),
            deconv_kernel_sizes=(4, 4))
        self.assertTrue(isinstance(head.deconv_layers, nn.Sequential))
        self.assertTrue(isinstance(head.conv_layers, nn.Identity))

        # w/ both deconv and conv
        head = HeatmapHead(
            in_channels=32,
            out_channels=17,
            deconv_out_channels=(32, 32),
            deconv_kernel_sizes=(4, 4),
            conv_out_channels=(32, ),
            conv_kernel_sizes=(1, ))
        self.assertTrue(isinstance(head.deconv_layers, nn.Sequential))
        self.assertTrue(isinstance(head.conv_layers, nn.Sequential))

        # w/o final layer
        head = HeatmapHead(
            in_channels=32, out_channels=17, has_final_layer=False)
        self.assertTrue(isinstance(head.final_layer, nn.Identity))

        # w/ decoder
        head = HeatmapHead(
            in_channels=32,
            out_channels=17,
            decoder=dict(
                type='MSRAHeatmap',
                input_size=(192, 256),
                heatmap_size=(48, 64),
                sigma=2.))
        self.assertIsNotNone(head.decoder)

    def test_predict(self):
        decoder_cfg = dict(
            type='MSRAHeatmap',
            input_size=(192, 256),
            heatmap_size=(48, 64),
            sigma=2.)

        # input transform: select
        head = HeatmapHead(
            in_channels=[16, 32],
            out_channels=17,
            input_transform='select',
            input_index=-1,
            decoder=decoder_cfg)
        feats = self._get_feats(
            batch_size=2, feat_shapes=[(16, 16, 12), (32, 8, 6)])
        batch_data_samples = self._get_data_samples(batch_size=2)
        preds = head.predict(feats, batch_data_samples)

        self.assertEqual(len(preds), 2)
        self.assertIsInstance(preds[0], PoseDataSample)
        self.assertIn('pred_instances', preds[0])
        self.assertEqual(preds[0].pred_instances.keypoints.shape,
                         preds[0].gt_instances.keypoints.shape)

        # input transform: resize and concat
        head = HeatmapHead(
            in_channels=[16, 32],
            out_channels=17,
            input_transform='resize_concat',
            input_index=[0, 1],
            deconv_out_channels=(256, 256),
            deconv_kernel_sizes=(4, 4),
            conv_out_channels=(256, ),
            conv_kernel_sizes=(1, ),
            decoder=decoder_cfg)
        feats = self._get_feats(
            batch_size=2, feat_shapes=[(16, 16, 12), (32, 8, 6)])
        batch_data_samples = self._get_data_samples(batch_size=2)
        preds = head.predict(feats, batch_data_samples)

        self.assertEqual(len(preds), 2)
        self.assertIsInstance(preds[0], PoseDataSample)
        self.assertIn('pred_instances', preds[0])
        self.assertEqual(preds[0].pred_instances.keypoints.shape,
                         preds[0].gt_instances.keypoints.shape)
        self.assertNotIn('pred_fields', preds[0])

        # input transform: output heatmap
        head = HeatmapHead(
            in_channels=[16, 32],
            out_channels=17,
            input_transform='select',
            input_index=-1,
            decoder=decoder_cfg)
        feats = self._get_feats(
            batch_size=2, feat_shapes=[(16, 16, 12), (32, 8, 6)])
        batch_data_samples = self._get_data_samples(batch_size=2)
        preds = head.predict(
            feats, batch_data_samples, test_cfg=dict(output_heatmaps=True))

        self.assertIn('pred_fields', preds[0])
        self.assertEqual(preds[0].pred_fields.heatmaps.shape, (17, 48, 64))

    def test_loss(self):
        head = HeatmapHead(
            in_channels=[16, 32],
            out_channels=17,
            input_transform='select',
            input_index=-1)

        feats = self._get_feats(
            batch_size=2, feat_shapes=[(16, 16, 12), (32, 8, 6)])
        batch_data_samples = self._get_data_samples(batch_size=2)
        losses = head.loss(feats, batch_data_samples)
        self.assertIsInstance(losses['loss_kpt'], torch.Tensor)
        self.assertEqual(losses['loss_kpt'].shape, torch.Size(()))
        self.assertIsInstance(losses['acc_pose'], np.float32)

    def test_errors(self):
        # Invalid arguments
        with self.assertRaisesRegex(ValueError, 'Got unmatched values'):
            _ = HeatmapHead(
                in_channels=[16, 32],
                out_channels=17,
                deconv_out_channels=(256, ),
                deconv_kernel_sizes=(4, 4))

        with self.assertRaisesRegex(ValueError, 'Got unmatched values'):
            _ = HeatmapHead(
                in_channels=[16, 32],
                out_channels=17,
                conv_out_channels=(256, ),
                conv_kernel_sizes=(1, 1))

        with self.assertRaisesRegex(ValueError, 'Unsupported kernel size'):
            _ = HeatmapHead(
                in_channels=[16, 32],
                out_channels=17,
                deconv_out_channels=(256, ),
                deconv_kernel_sizes=(2, ))

        # Select multiple features
        head = HeatmapHead(
            in_channels=[16, 32],
            out_channels=17,
            input_transform='select',
            input_index=[0, 1])

        feats = self._get_feats(
            batch_size=2, feat_shapes=[(16, 16, 12), (32, 8, 6)])

        with self.assertRaisesRegex(AssertionError,
                                    'Selecting multiple features'):
            _ = head.forward(feats)

    def test_state_dict_compatible(self):
        # Typical setting for HRNet
        head = HeatmapHead(
            in_channels=32, out_channels=17, deconv_out_channels=None)

        state_dict = {
            'final_layer.weight': torch.zeros((17, 32, 1, 1)),
            'final_layer.bias': torch.zeros((17))
        }
        head.load_state_dict(state_dict)

        # Typical setting for Resnet
        head = HeatmapHead(in_channels=2048, out_channels=17)

        state_dict = {
            'deconv_layers.0.weight': torch.zeros([2048, 256, 4, 4]),
            'deconv_layers.1.weight': torch.zeros([256]),
            'deconv_layers.1.bias': torch.zeros([256]),
            'deconv_layers.1.running_mean': torch.zeros([256]),
            'deconv_layers.1.running_var': torch.zeros([256]),
            'deconv_layers.1.num_batches_tracked': torch.zeros([]),
            'deconv_layers.3.weight': torch.zeros([256, 256, 4, 4]),
            'deconv_layers.4.weight': torch.zeros([256]),
            'deconv_layers.4.bias': torch.zeros([256]),
            'deconv_layers.4.running_mean': torch.zeros([256]),
            'deconv_layers.4.running_var': torch.zeros([256]),
            'deconv_layers.4.num_batches_tracked': torch.zeros([]),
            'deconv_layers.6.weight': torch.zeros([256, 256, 4, 4]),
            'deconv_layers.7.weight': torch.zeros([256]),
            'deconv_layers.7.bias': torch.zeros([256]),
            'deconv_layers.7.running_mean': torch.zeros([256]),
            'deconv_layers.7.running_var': torch.zeros([256]),
            'deconv_layers.7.num_batches_tracked': torch.zeros([]),
            'final_layer.weight': torch.zeros([17, 256, 1, 1]),
            'final_layer.bias': torch.zeros([17])
        }
        head.load_state_dict(state_dict)