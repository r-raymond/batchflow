import sys
import tensorflow as tf

sys.path.append("../../..")
from batchflow import Pipeline, B, C, V
from batchflow.opensets import MNIST
from batchflow.models.tf import VGG7, VGG16
from batchflow.research import Research, Option

BATCH_SIZE=64

model_config={
    'session/config': tf.ConfigProto(allow_soft_placement=True),
    'inputs': dict(images={'shape': (28, 28, 1)},
                   labels={'classes': 10, 'transform': 'ohe', 'name': 'targets'}),
    'initial_block/inputs': 'images',
    'body/block/layout': C('layout'),
    'device': C('tf_device') # it's technical parameter for TFModel
}

mnist = MNIST()
train_root = mnist.train.p.run(BATCH_SIZE, shuffle=True, n_epochs=None, lazy=True)
test_root = mnist.test.p.run(BATCH_SIZE, shuffle=True, n_epochs=1, lazy=True)

train_template = (Pipeline()
            .init_variable('loss', init_on_each_run=list)
            .init_variable('accuracy', init_on_each_run=list)
            .init_model('dynamic', C('model'), 'conv', config=model_config)
            .to_array()
            .train_model('conv', 
                         fetches='loss', 
                         feed_dict={'images': B('images'), 'labels': B('labels')},
                         save_to=V('loss'), mode='w')
)

test_template = (Pipeline()
            .init_variable('predictions') 
            .init_variable('metrics', init_on_each_run=None) 
            .import_model('conv', C('import_from'))
            .to_array()
            .predict_model('conv', 
                         fetches='predictions', 
                         feed_dict={'images': B('images'), 'labels': B('labels')},
                         save_to=V('predictions'))
            .gather_metrics('class', targets=B('labels'), predictions=V('predictions'),
                                fmt='logits', axis=-1, save_to=V('metrics'), mode='a')
)

train_ppl = train_root + train_template
test_ppl = test_root + test_template

grid = Option('layout', ['cna', 'can']) * Option('model', [VGG7, VGG16])

def get_accuracy(iteration, experiment, pipeline):
    pipeline = experiment[pipeline].pipeline
    metrics = pipeline.get_variable('metrics')
    return metrics.evaluate('accuracy')

research = (Research()
    .add_pipeline(root=train_root, branch=train_template, variables='loss', name='train')
    .add_pipeline(root=test_root, branch=test_template, name='test', run=True, execute='%100', import_from='train')
    .add_grid(grid)
    .add_function(get_accuracy, returns='accuracy', name='test_accuracy', execute='%100', pipeline='test')
)

n_workers = 1 if len(sys.argv) <= 1 else int(sys.argv[1])
gpu_list = [2, 4, 5, 6] if len(sys.argv) <= 2 else [int(item) for item in sys.argv[2]]

research.run(n_reps=1, n_iters=1000, workers=n_workers, name='my_research', gpu=gpu_list[:n_workers])
