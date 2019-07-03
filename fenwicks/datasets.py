from .imports import *
from urllib.parse import urlparse

__all__ = ['URLs', 'untar_data']


class URLs:
    FASTAI = 'http://files.fast.ai/data/'
    FASTAI_S3 = 'https://s3.amazonaws.com/fast-ai-'
    FASTAI_S3_IMAGE = f'{FASTAI_S3}imageclas/'

    DVC = f'{FASTAI}dogscats.zip'
    PETS = f'{FASTAI_S3_IMAGE}oxford-iiit-pet.tgz'

    TF = 'http://download.tensorflow.org/'
    SPEECH_CMD_001 = f'{TF}data/speech_commands_v0.01.tar.gz'
    SPEECH_CMD_002 = f'{TF}data/speech_commands_v0.02.tar.gz'
    FLOWER_PHOTOS = f'{TF}example_images/flower_photos.tgz'

    KAGGLE_COMPETITION_DOWNLOAD = 'competitions download -c '
    KAGGLE_DATASETS_DOWNLOAD = 'datasets download -d '

    KAGGLE_CIFAR10 = f'{KAGGLE_COMPETITION_DOWNLOAD}cifar-10'
    KAGGLE_IMDB = f'{KAGGLE_COMPETITION_DOWNLOAD}word2vec-nlp-tutorial'
    KAGGLE_DIABETIC_RETINOPATHY = f'{KAGGLE_COMPETITION_DOWNLOAD}diabetic-retinopathy-detection'
    KAGGLE_CARDIAC_FUNCTION = f'{KAGGLE_COMPETITION_DOWNLOAD}second-annual-data-science-bowl'
    KAGGLE_RSNA_PNEUMONIA_DETECTION = f'rsna-pneumonia-detection-challenge'

    KAGGLE_SKIN_CANCER = f'{KAGGLE_DATASETS_DOWNLOAD}kmader/skin-cancer-mnist-ham10000'
    KAGGLE_BONE_AGE = f'{KAGGLE_DATASETS_DOWNLOAD}kmader/rsna-bone-age'
    KAGGLE_PNEUMONIA = f'{KAGGLE_DATASETS_DOWNLOAD}paultimothymooney/chest-xray-pneumonia'

    GLUE = 'https://firebasestorage.googleapis.com/v0/b/mtl-sentence-representations.appspot.com/o/data%2F'
    GLUE_COLA = f'{GLUE}CoLA.zip?alt=media&token=46d5e637-3411-4188-bc44-5809b5bfb5f4'
    GLUE_MRPC = f'{GLUE}mrpc_dev_ids.tsv?alt=media&token=ec5c0836-31d5-48f4-b431-7480817f1adc'

    MRPC_TRAIN = 'https://dl.fbaipublicfiles.com/senteval/senteval_data/msr_paraphrase_train.txt'
    MRPC_TEST = 'https://dl.fbaipublicfiles.com/senteval/senteval_data/msr_paraphrase_test.txt'


def untar_data(url: str, dest: str = '.', fn: str = None) -> str:
    if not gfile.isdir(dest):
        gfile.makedirs(dest)
    url_path = urlparse(url).path
    fn = fn if fn else os.path.basename(url_path)
    data_dir = os.path.join(dest, 'datasets')
    if not gfile.exists(os.path.join(data_dir, fn)):
        tf.keras.utils.get_file(fn, origin=url, extract=True, cache_dir=dest)
    return data_dir