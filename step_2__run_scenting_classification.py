###### IMPORTS ######
# General
import os
import sys
import cv2
import glob
import json
import argparse
import pandas as pd
import numpy as np

# Pytorch
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import SubsetRandomSampler

import torchvision
import torchvision.models
import torchvision.transforms as transforms

# Import other python files
import scenting_classification.modules.Utils as Utils
import scenting_classification.modules.DataHandler as DataHandler
import scenting_classification.modules.DataSamplers as DataSamplers
import scenting_classification.modules.EvaluationUtils as Evaluation

import utils.general as general_utils

def build_resnet(num_classes):
    print(f"Building resnet-18 with {num_classes} classes...")
    resnet = torchvision.models.resnet18(pretrained=True)
    num_ftrs = resnet.fc.in_features
    resnet.fc = nn.Linear(num_ftrs, num_classes)
    return resnet

def predict(bee_data, data_loader, model, device, batch_size):
    classifications = list(np.zeros(len(bee_data.data_df)))
    counter = 0
    try:
        for i, (X, y, experiment, frame, crop) in enumerate(data_loader):
            sys.stdout.write(f'\rBatch {i+1} / {len(data_loader)}')
            sys.stdout.flush()

            X = Utils.convert_X_for_resnet(X)
            X = X.to(device)
            y = y.to(device)
            logits = model(X)
            preds = Utils.get_prediction(logits)
            pred_strings = Utils.get_labels(bee_data, preds)

            for img_i in range(batch_size):
                if counter < len(bee_data.data_df):
                    classifications[counter] = pred_strings[img_i]
                    counter += 1
    except KeyboardInterrupt:
        print('\nEnding early.')
    return classifications

def save_prediction(bee_data, classifications, folder_paths):
    bee_data.data_df['classification'] = classifications
    labeled_h5 = bee_data.data_df.to_dict('list')
    resnet_save_path = os.path.join(folder_paths[0], 'data_log_scenting.json')
    with open(resnet_save_path, 'w') as outfile:
        json.dump(labeled_h5, outfile)
        outfile.close()

def setup_args():
    parser = argparse.ArgumentParser(description='Classify scenting bees!')
    parser.add_argument('-p', '--data_root', dest='data_root', type=str, default='data/processed')
    parser.add_argument('-m', '--model_file', dest='model_file', type=str, default='ResnetScentingModel.pt')
    parser.add_argument('-b', '--batch_size', dest='batch_size', type=int, default=32)
    parser.add_argument('-c', '--num_classes', dest='num_classes', type=int, default=2)
    args = parser.parse_args()
    return args

def main(args):
    # Select the video
    print("-- Select video from list...")
    src_processed_root = general_utils.select_file(args.data_root)
    print(f'\nProcessing video: {src_processed_root}')

    print("\n---------- Classifying scenting bees ----------")
    # ResNet model path
    load_path = f'scenting_classification/saved_models/{args.model_file}'

    # Obtain up paths for video folder
    vid_name = src_processed_root.split('/')[-1]
    folder_paths = glob.glob(f'{args.data_root}/{vid_name}*')
    json_paths = sorted([os.path.join(folder, f'data_log.json') for folder in folder_paths])
    frames_path = f'denoised_frames/'

    # ------------------------------------------------------------- #
    ##### DATASET & TRANSFORMS ######
    # Set default transforms
    baseline_transforms = transforms.Compose([transforms.ToTensor()])

    # Instantiate object for data
    print(f'Setting up data handler...')
    bee_data = DataHandler.BeeDataset_2(args.data_root, json_paths, frames_path,
                          baseline_transforms, augment_transforms=None, mode='eval')
    print(f'Number of bee images to process: {len(bee_data)}\n')

    # ------------------------------------------------------------- #
    ###### DATALOADER ######
    print(f'Setting up data loader...\n')
    # Batch size
    batch_size = args.batch_size
    test_idxs = np.arange(0, len(bee_data))
    sampler_test = DataSamplers.SubsetIdentitySampler(indices=test_idxs)
    data_loader = DataLoader(bee_data, batch_size=batch_size, sampler=sampler_test, drop_last=False)

    # ------------------------------------------------------------- #
    ###### MODEL ######
    num_classes = args.num_classes
    model = build_resnet(num_classes)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f'Running on device: {device}\n')

    # ------------------------------------------------------------- #
    ###### LOAD TRAINED MODEL ######
    print(f"Loading trained model...\n")
    load_dict = torch.load(load_path, map_location=device)
    model.load_state_dict(load_dict['model'])
    metrics = load_dict['metrics']
    model.eval();
    model.to(device);

    # ------------------------------------------------------------- #
    ###### RUN TRAINED MODEL ######
    print(f"Classifying bee images as scenting/non-scenting...")
    classifications = predict(bee_data, data_loader, model, device, batch_size)

    # ------------------------------------------------------------- #
    ###### SAVED OUTPUT DATA ######
    print(f'\nSaving scenting classifications...')
    save_prediction(bee_data, classifications, folder_paths)
    print(f"Fin.")

if __name__ == '__main__':
    args = setup_args()
    main(args)
    print("\n")
