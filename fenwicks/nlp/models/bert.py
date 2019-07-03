from ...imports import *

from .. import tokenizer

from ... import layers, io


def transformer(x: tf.Tensor, attn_mask: tf.Tensor = None, c: int = 768, n_hidden_layers=12, n_heads: int = 12,
                ff_c: int = 3072, ff_act: Callable = F.gelu, hidden_dropout_prob: float = 0.1,
                attn_dropout_prob: float = 0.1, return_all_layers: bool = False) -> Union[List[tf.Tensor], tf.Tensor]:
    input_shape = core.get_shape_list(x)  # [bs, seq_len, c]
    x_2d = core.reshape_to_matrix(x)

    attn_c = c // n_heads
    bs, seq_len = input_shape[0], input_shape[1]

    all_layer_outputs = []
    for layer_idx in range(n_hidden_layers):
        with tf.variable_scope(f"layer_{layer_idx}"):
            with tf.variable_scope("attention"):
                with tf.variable_scope("self"):
                    attn_h = layers.attention(src=x_2d, dest=x_2d, mask=attn_mask, n_heads=n_heads, c=attn_c,
                                              dropout_prob=attn_dropout_prob, return_2d=True, bs=bs, src_len=seq_len,
                                              dest_len=seq_len)

                with tf.variable_scope("output"):
                    attn_h = tf.layers.dense(attn_h, c)
                    attn_h = F.dropout(attn_h, hidden_dropout_prob)
                    attn_h = layers.layer_norm(attn_h + x_2d)

            with tf.variable_scope("intermediate"):
                ff_h = tf.layers.dense(attn_h, ff_c, activation=ff_act)

            with tf.variable_scope("output"):
                h = tf.layers.dense(ff_h, c)
                h = F.dropout(h, hidden_dropout_prob)
                h = layers.layer_norm(h + attn_h)
                x_2d = h
                all_layer_outputs.append(h)

    reshape_func = functools.partial(core.reshape_from_matrix, orig_shape_list=input_shape)
    return list(map(reshape_func, all_layer_outputs)) if return_all_layers else reshape_func(x_2d)


def word_emb(x: tf.Tensor, vocab_size: int, c: int = 768, one_hot: bool = False) -> tf.Tensor:
    if x.shape.ndims == 2:
        x = tf.expand_dims(x, axis=[-1])  # todo: change input_shape instead of reshape
    input_shape = core.get_shape_list(x)
    x_flat = tf.reshape(x, [-1])

    embedding_table = tf.get_variable(name="word_embeddings", shape=[vocab_size, c])

    if one_hot:
        one_hot_input_ids = tf.one_hot(x_flat, depth=vocab_size)
        x = tf.matmul(one_hot_input_ids, embedding_table)
    else:
        x = tf.gather(embedding_table, x_flat)

    x = tf.reshape(x, input_shape[0:-1] + [input_shape[-1] * c])
    return x


def token_type_pos_emb(x: tf.Tensor, token_type_ids: tf.Tensor, token_type_vocab_size: int = 16, max_seq_len: int = 512,
                       dropout_prob: float = 0.1):
    input_shape = core.get_shape_list(x)
    bs, seq_len, c = input_shape[0], input_shape[1], input_shape[2]

    token_type_table = tf.get_variable(name="token_type_embeddings", shape=[token_type_vocab_size, c])
    flat_token_type_ids = tf.reshape(token_type_ids, [-1])
    one_hot_ids = tf.one_hot(flat_token_type_ids, depth=token_type_vocab_size)
    token_type_emb = tf.matmul(one_hot_ids, token_type_table)
    token_type_emb = tf.reshape(token_type_emb, [bs, seq_len, c])
    x += token_type_emb

    full_pos_emb = tf.get_variable(name="position_embeddings", shape=[max_seq_len, c])
    pos_emb = tf.slice(full_pos_emb, [0, 0], [seq_len, -1])
    x += pos_emb
    return layers.layer_norm_and_dropout(x, dropout_prob)


# todo: only thing we use from src is its shape
def create_attention_mask(src: tf.Tensor, dest_mask: tf.Tensor):
    src_shape = core.get_shape_list(src)  # [bs, src_len, ...]
    desk_shape = core.get_shape_list(dest_mask)  # [bs, dest_len], int32
    bs, src_len, dest_len = src_shape[0], src_shape[1], desk_shape[1]

    dest_mask = tf.cast(tf.reshape(dest_mask, [bs, 1, dest_len]), tf.float32)
    return tf.ones(shape=[bs, src_len, 1], dtype=tf.float32) * dest_mask  # [bs, src_len, dest_len]


class BertConfig:
    def __init__(self, vocab_size: int = 0, hidden_size: int = 768, num_hidden_layers: int = 12,
                 num_attention_heads: int = 12, intermediate_size: int = 3072, hidden_dropout_prob: float = 0.1,
                 attention_probs_dropout_prob: float = 0.1, max_position_embeddings: int = 512,
                 type_vocab_size: int = 16):
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.max_position_embeddings = max_position_embeddings
        self.type_vocab_size = type_vocab_size


class BertModel(tf.keras.Model):
    def __init__(self, config: BertConfig, one_hot_in_word_emb: bool = False):
        super().__init__()
        self.config = copy.deepcopy(config)
        self.one_hot_in_word_emb = one_hot_in_word_emb

    def call(self, x: Dict[str, tf.Tensor], *args, **kw_args) -> tf.Tensor:
        config = self.config
        if tf.keras.backend.learning_phase() == 0:
            config.hidden_dropout_prob = 0.0
            config.attention_probs_dropout_prob = 0.0

        input_ids = x['token_ids']
        input_mask = x['mask']

        input_shape = core.get_shape_list(input_ids)
        batch_size, seq_length = input_shape[0], input_shape[1]
        token_type_ids = x['token_type_ids'] if 'token_type_ids' in x else tf.ones(shape=[batch_size, seq_length],
                                                                                   dtype=tf.int32)

        if token_type_ids is None:
            token_type_ids = tf.zeros(shape=[batch_size, seq_length], dtype=tf.int32)

        with tf.variable_scope("bert"):
            with tf.variable_scope("embeddings"):
                h = word_emb(input_ids, vocab_size=config.vocab_size, c=config.hidden_size,
                             one_hot=self.one_hot_in_word_emb)

                h = token_type_pos_emb(h, token_type_ids=token_type_ids, token_type_vocab_size=config.type_vocab_size,
                                       max_seq_len=config.max_position_embeddings,
                                       dropout_prob=config.hidden_dropout_prob)

            with tf.variable_scope("encoder"):
                attn_mask = create_attention_mask(input_ids, input_mask)  # [batch_size, seq_length, seq_length]

                all_encoder_layers = transformer(h, attn_mask=attn_mask, c=config.hidden_size,
                                                 n_hidden_layers=config.num_hidden_layers,
                                                 n_heads=config.num_attention_heads, ff_c=config.intermediate_size,
                                                 hidden_dropout_prob=config.hidden_dropout_prob,
                                                 attn_dropout_prob=config.attention_probs_dropout_prob,
                                                 return_all_layers=True)
            sequence_output = all_encoder_layers[-1]  # [batch_size, seq_length, hidden_size].

            with tf.variable_scope("pooler"):
                first_token = tf.squeeze(sequence_output[:, 0:1, :], axis=1)
                pooled_output = tf.layers.dense(first_token, config.hidden_size, activation=tf.tanh)

        return pooled_output


def unreachable_ops(graph, outputs):
    outputs = core.flatten_recursive(outputs)
    output_to_op = collections.defaultdict(list)
    op_to_all = collections.defaultdict(list)
    assign_out_to_in = collections.defaultdict(list)

    for op in graph.get_operations():
        for x in op.inputs:
            op_to_all[op.name].append(x.name)
        for y in op.outputs:
            output_to_op[y.name].append(op.name)
            op_to_all[op.name].append(y.name)
        if str(op.type) == "Assign":
            for y in op.outputs:
                for x in op.inputs:
                    assign_out_to_in[y.name].append(x.name)

    assign_groups = collections.defaultdict(list)
    for out_name in assign_out_to_in.keys():
        name_group = assign_out_to_in[out_name]
        for n1 in name_group:
            assign_groups[n1].append(out_name)
            for n2 in name_group:
                if n1 != n2:
                    assign_groups[n1].append(n2)

    seen_tensors = {}
    stack = [x.name for x in outputs]
    while stack:
        name = stack.pop()
        if name in seen_tensors:
            continue
        seen_tensors[name] = True

        if name in output_to_op:
            for op_name in output_to_op[name]:
                if op_name in op_to_all:
                    for input_name in op_to_all[op_name]:
                        if input_name not in stack:
                            stack.append(input_name)

        expanded_names = []
        if name in assign_groups:
            for assign_name in assign_groups[name]:
                expanded_names.append(assign_name)

        for expanded_name in expanded_names:
            if expanded_name not in stack:
                stack.append(expanded_name)

    results = []
    for op in graph.get_operations():
        is_unreachable = False
        all_names = [x.name for x in op.inputs] + [x.name for x in op.outputs]
        for name in all_names:
            if name not in seen_tensors:
                is_unreachable = True
        if is_unreachable:
            results.append(op)
    return results


def download_vocab(model_name: str = 'uncased_L-12_H-768_A-12') -> str:
    bert_model_hub = f'https://tfhub.dev/google/bert_{model_name}/1'
    with tf.Graph().as_default():
        import tensorflow_hub as hub
        bert_module = hub.Module(bert_model_hub)
        tokenization_info = bert_module(signature="tokenization_info", as_dict=True)
        with tf.Session() as sess:
            vocab_fn = sess.run(tokenization_info["vocab_file"])
    return vocab_fn


def get_tokenizer(model_name: str = 'uncased_L-12_H-768_A-12') -> tokenizer.BertTokenizer:
    vocab_fn = download_vocab(model_name)
    uncased = model_name.startswith('uncased')
    return tokenizer.BertTokenizer(vocab_fn=vocab_fn, do_lower_case=uncased)


def get_bert_model(model_name: str = 'uncased_L-12_H-768_A-12') -> Tuple[BertConfig, str, tokenizer.BertTokenizer]:
    ckpt_dir = f'gs://cloud-tpu-checkpoints/bert/{model_name}'
    cfg_fn = os.path.join(ckpt_dir, 'bert_config.json')
    ckpt_fn = os.path.join(ckpt_dir, 'bert_model.ckpt')

    cfg = io.from_json(BertConfig, cfg_fn)
    tokenizer = get_tokenizer(model_name)
    return cfg, ckpt_fn, tokenizer