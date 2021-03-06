# coding:utf8
from __future__ import division
from __future__ import print_function

from models import get_end_net, get_encoder_net, CNNencoder
from config import cfg
from opts import parse_opts

import os
import torch
from torch import nn
from torch.optim import lr_scheduler
from spatial_transforms import (
    Compose, Normalize, Scale, CenterCrop, CornerCrop, MultiScaleCornerCrop,
    MultiScaleRandomCrop, RandomHorizontalFlip, ToTensor)
from temporal_transforms import LoopPadding, TemporalRandomCrop
from target_transforms import ClassLabel
from dataset import get_training_set, get_validation_set
from tensorboard_logger import Logger
from log_utils import get_log_dir
from train import train_epoch
from validation import val_epoch


def main():
    opt = parse_opts()

    ecd_name, cls_name = opt.model_name.split('-')
    ecd_model = get_encoder_net(ecd_name)
    cls_model = get_end_net(cls_name)

    cfg.encoder_model = ecd_name
    cfg.classification_model = cls_name

    if opt.debug:
        cfg.debug = opt.debug
    else:
        if opt.tensorboard == 'TEST':
            cfg.tensorboard = opt.model_name
        else:
            cfg.tensorboard = opt.tensorboard
            cfg.flag = opt.flag
    model = cls_model(cfg, encoder=CNNencoder(cfg, ecd_model(pretrained=True, path=opt.encoder_model)))
    cfg.video_path = os.path.join(cfg.root_path, cfg.video_path)
    cfg.annotation_path = os.path.join(cfg.root_path, cfg.annotation_path)

    cfg.list_all_member()

    torch.manual_seed(cfg.manual_seed)
    print('##########################################')
    print('####### model 仅支持单GPU')
    print('##########################################')
    model = model.cuda()
    print(model)
    criterion = nn.CrossEntropyLoss()
    if cfg.cuda:
        criterion = criterion.cuda()

    norm_method = Normalize([0, 0, 0], [1, 1, 1])

    print('##########################################')
    print('####### train')
    print('##########################################')
    assert cfg.train_crop in ['random', 'corner', 'center']
    if cfg.train_crop == 'random':
        crop_method = (cfg.scales, cfg.sample_size)
    elif cfg.train_crop == 'corner':
        crop_method = MultiScaleCornerCrop(cfg.scales, cfg.sample_size)
    elif cfg.train_crop == 'center':
        crop_method = MultiScaleCornerCrop(
            cfg.scales, cfg.sample_size, crop_positions=['c'])
    spatial_transform = Compose([
        crop_method,
        RandomHorizontalFlip(),
        ToTensor(cfg.norm_value), norm_method
    ])
    temporal_transform = TemporalRandomCrop(cfg.sample_duration)
    target_transform = ClassLabel()
    training_data = get_training_set(cfg, spatial_transform,
                                     temporal_transform, target_transform)
    train_loader = torch.utils.data.DataLoader(
        training_data,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.n_threads,
        drop_last=False,
        pin_memory=True)
    optimizer = model.get_optimizer(lr1=cfg.lr, lr2=cfg.lr2)
    scheduler = lr_scheduler.ReduceLROnPlateau(
        optimizer, 'min', patience=cfg.lr_patience)
    print('##########################################')
    print('####### val')
    print('##########################################')
    spatial_transform = Compose([
        Scale(cfg.sample_size),
        CenterCrop(cfg.sample_size),
        ToTensor(cfg.norm_value), norm_method
    ])
    temporal_transform = LoopPadding(cfg.sample_duration)
    target_transform = ClassLabel()
    validation_data = get_validation_set(
        cfg, spatial_transform, temporal_transform, target_transform)
    val_loader = torch.utils.data.DataLoader(
        validation_data,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.n_threads,
        drop_last=False,
        pin_memory=True)
    print('##########################################')
    print('####### run')
    print('##########################################')
    if cfg.debug:
        logger = None
    else:
        path = get_log_dir(cfg.logdir, name=cfg.tensorboard, flag=cfg.flag)
        logger = Logger(logdir=path)
        cfg.save_config(path)

    for i in range(cfg.begin_epoch, cfg.n_epochs + 1):
        train_epoch(i, train_loader, model, criterion, optimizer, cfg, logger)
        validation_loss = val_epoch(i, val_loader, model, criterion, cfg, logger)

        scheduler.step(validation_loss)


if __name__ == '__main__':
    main()
