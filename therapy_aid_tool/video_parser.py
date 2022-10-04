from __future__ import annotations

from collections import defaultdict
from itertools import groupby

from therapy_aid_tool.model_inference import (
    load_model, preds_from_torch_results, MODEL_SIZE, BBox)

import cv2


class VideoParser:
    """Extract information about what is happening in the ASD video session
    """

    def __init__(self, video_path: str, n_classes: int = 6) -> None:
        self.cap = cv2.VideoCapture(video_path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.n_classes = n_classes
        self.bbs = self.bboxes()

    def bboxes(self):
        """Return present bounding boxes for each frame

        The output is stored in a dictionary (defaultdict) with the 
        keys being the actual classes of detection available, for
        now there are 6 classes divide in two fields, actors and
        interactions. 
            Actors: toddler, caretaker and plusme
            interactions: toddler-caretaker,
                          toddler-plusme,
                          and caretaker-plusme.

        Each bounding box, being a instance of a BBox, can be used to
        extract its coordinates and other parameters to detect how 
        close actors are. It can be used also to detect if there are 
        interactions happening, or to plot rectangular regions if desired.

        Returns:
            defaultdict: Bounding boxes for each frame. The keys are the
                classes and the values are arrays/lists contaning a BBox
                instance for that class key in that frame index.

                Return example: {
                    'td': [BBox0, BBox1, ...], 
                    'ct': [BBox0, BBox1, ...], 
                    'pm': [BBox0, BBox1, ...],
                    'td_ct_interaction': [BBox0, BBox1, ...],
                    'td_pm_interaction': [BBox0, BBox1, ...],
                    'ct_pm_interaction': [BBox0, BBox1, ...]
                    }
        """
        model = load_model()
        bbs = defaultdict(list)

        for i in range(self.total_frames):
            _, frame = self.cap.read()
            inference = model(frame[:, :, ::-1], size=MODEL_SIZE)
            preds = preds_from_torch_results(
                inference, self.n_classes)  # returns six raw preds

            bbs['td'].append(BBox(preds[0]))
            bbs['ct'].append(BBox(preds[1]))
            bbs['pm'].append(BBox(preds[2]))
            bbs['td_ct_interaction'].append(BBox(preds[3]))
            bbs['td_pm_interaction'].append(BBox(preds[4]))
            bbs['ct_pm_interaction'].append(BBox(preds[5]))

        return bbs

    def closeness(self):
        """Return how close actors' bounding box pairs are based on NIoU for each frame

        To measure how close two different objects are based on their bounding boxes we
        can use the Normalized Intersection over Union.

        This metric is measured for each pair of actors relation for each frame and
        return in form of a dictionary.

        This results can generate a "YouTube" like bar of "best" moments, or in our case,
        moments of closeness.

        Returns:
            defaultdict: How much close are the three main actors for each frame.
                The keys are the three relation classes available and the values 
                are arrays/lists containing a float between 0~1 for that class key 
                in that frame index

                Return example: {
                    'td_ct': [NIoU0(td, ct), NIoU1(td, ct), ...],
                    'td_pm': [NIoU0(td, pm), NIoU1(td, pm), ...],
                    'ct_pm': [NIoU0(ct, pm), NIoU1(ct, pm), ...]
                    }
        """
        #
        closeness = defaultdict(list)
        bbs = self.bbs

        for idx in range(self.total_frames):
            closeness['td_ct'].append(bbs['td'][idx].niou(bbs['ct'][idx]))
            closeness['td_pm'].append(bbs['td'][idx].niou(bbs['pm'][idx]))
            closeness['ct_pm'].append(bbs['ct'][idx].niou(bbs['pm'][idx]))

        return closeness

    def interactions(self):
        """Return if there is an interaction present for each frame

        Interaction is a type of detection that is currently made alongside the
        actors. Its presence indicates that one actors is engaging in physical touch
        with another. Like the toddler touching the plusme teddy bear or the caretaker
        showing the toddler how to play with the teddy bear.

        For each frame, return a Bool indicating if there is that respective interaction,
        making an array of bools for one interaction class

        Returns:
            defaultdict: The interactions for each frame.
                The keys are the three relation classes available and the values 
                are arrays/lists containing a Bool for that class key in that frame index

                Return example: {
                    'td_ct': [Bool, Bool, ...],
                    'td_pm': [Bool, Bool, ...],
                    'ct_pm': [Bool, Bool, ...]
                    }
        """
        interactions = defaultdict(list)
        bbs = self.bbs

        for idx in range(self.total_frames):
            interactions['td_ct'].append(
                True if bbs['td_ct_interaction'][idx] else False)
            interactions['td_pm'].append(
                True if bbs['td_pm_interaction'][idx] else False)
            interactions['ct_pm'].append(
                True if bbs['ct_pm_interaction'][idx] else False)

        return interactions

    def interactions_statistics(self, interactions: dict):
        """Return statistics for the interactions in the video

        Args:
            interactions (dict): The interactions for each frame.
                The keys are the three relation classes available and the values 
                are arrays/lists containing a Bool for that class key in that frame index

                Example: {
                    'td_ct': [Bool, Bool, ...],
                    'td_pm': [Bool, Bool, ...],
                    'ct_pm': [Bool, Bool, ...]
                }

        Returns:
            dict: Statistics for all the interactions instances that happened in the video
                It can be used in a pandas.DataFrame to output a chart view.       
        """
        frame_time = 1/self.fps  # time one frame takes to run

        statistics = {
            'td_ct': {'n_interactions': int, 'total_time': float, 'min_time': float, 'max_time': float, 'mean_time': float},
            'td_pm': {'n_interactions': int, 'total_time': float, 'min_time': float, 'max_time': float, 'mean_time': float},
            'ct_pm': {'n_interactions': int, 'total_time': float, 'min_time': float, 'max_time': float, 'mean_time': float}
        }

        for key, interaction in interactions.items():
            # Groups of interaction and non interactions (1s and 0s)
            groups = groupby(interaction)

            # Generate metrics for interaction
            groups_of_interaction = []  # the chunks of 1s
            idxs = []  # start and end indexes of each chunk
            count = 0  # auxiliary to get indexes
            for k, group in groups:
                group = list(group)
                count += len(group)
                if k == 1:
                    idx1 = count - len(group)
                    idx2 = count
                    idxs.append((idx1, idx2))
                    groups_of_interaction.append(group)

            if groups_of_interaction:
                n_interactions = len(groups_of_interaction)
                total_time = interaction.count(1) * frame_time
                mean_time = total_time / len(groups_of_interaction)
                max_time = len(max(groups_of_interaction)) * frame_time
                min_time = len(min(groups_of_interaction)) * frame_time
            else:
                n_interactions, total_time, mean_time, max_time, min_time = None, None, None, None, None

            statistics[key]['n_interactions'] = n_interactions
            statistics[key]['total_time'] = total_time
            statistics[key]['min_time'] = min_time
            statistics[key]['max_time'] = max_time
            statistics[key]['mean_time'] = mean_time

        return statistics
