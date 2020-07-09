from typing import List, Dict, Union
from transformers import AutoModel, AutoTokenizer
from transformers.tokenization_utils import BatchEncoding
from transformers.tokenization_utils_fast import PreTrainedTokenizerFast
import catalogue
from spacy.util import registry
from thinc.api import get_current_ops, CupyOps


registry.span_getters = catalogue.create("spacy", "span_getters", entry_points=True)
registry.annotation_setters = catalogue.create(
    "spacy", "annotation_setters", entry_points=True
)


def huggingface_from_pretrained(source, config):
    tokenizer = AutoTokenizer.from_pretrained(source, **config)
    transformer = AutoModel.from_pretrained(source)
    ops = get_current_ops()
    if isinstance(ops, CupyOps):
        transformer.cuda()
    return tokenizer, transformer


def huggingface_tokenize(tokenizer, texts: List[str]) -> BatchEncoding:
    token_data = tokenizer.batch_encode_plus(
        texts,
        add_special_tokens=True,
        return_attention_mask=True,
        return_length=True,
        return_offsets_mapping=isinstance(tokenizer, PreTrainedTokenizerFast),
        return_tensors="pt",
        return_token_type_ids=None,  # Sets to model default
        pad_to_max_length=True,
    )
    token_data["input_texts"] = [
        tokenizer.convert_ids_to_tokens(list(ids)) for ids in token_data["input_ids"]
    ]
    return token_data


def slice_hf_tokens(inputs: BatchEncoding, start: int, end: int) -> Dict:
    output = {}
    for key, value in inputs.items():
        if not hasattr(value, "__getitem__"):
            output[key] = value
        else:
            output[key] = value[start:end]
    return output


def find_last_hidden(tensors) -> int:
    for i, tensor in reversed(list(enumerate(tensors))):
        if len(tensor.shape) == 3:
            return i
    else:
        raise ValueError("No 3d tensors")


def transpose_list(nested_list):
    output = []
    for i, entry in enumerate(nested_list):
        while len(output) < len(entry):
            output.append([None] * len(nested_list))
        for j, x in enumerate(entry):
            output[j][i] = x
    return output


def batch_by_length(seqs, max_words: int) -> List[List[int]]:
    """Given a list of sequences, return a batched list of indices into the 
    list, where the batches are grouped by length, in descending order.
    
    Batches may be at most max_words in size, defined as max sequence length * size.
    """
    # Use negative index so we can get sort by position ascending.
    lengths_indices = [(len(seq), i) for i, seq in enumerate(seqs)]
    lengths_indices.sort()
    batches: List[List[int]] = []
    batch: List[int] = []
    for length, i in lengths_indices:
        if not batch:
            batch.append(i)
        elif length * (len(batch) + 1) <= max_words:
            batch.append(i)
        else:
            batches.append(batch)
            batch = [i]
    if batch:
        batches.append(batch)
    # Check lengths match
    assert sum(len(b) for b in batches) == len(seqs)
    # Check no duplicates
    seen = set()
    for b in batches:
        seen.update(id(item) for item in b)
    assert len(seen) == len(seqs)
    batches = [list(sorted(batch)) for batch in batches]
    batches.reverse()
    return batches
