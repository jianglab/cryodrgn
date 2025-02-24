import os.path
import numpy as np
import torch
import pytest
from cryodrgn.source import ImageSource, MRCFileSource


@pytest.fixture
def mrcs_data():
    return ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections.mrcs"), lazy=False
    ).images()


def test_loading_mrcs(mrcs_data):
    # 100 30x30 images
    src = ImageSource.from_file(os.path.join(pytest.DATADIR, "toy_projections.mrcs"))
    # Indexing inside the 'images' attributes causes the hitherto lazy data to turn into a Tensor
    assert torch.allclose(src[:], mrcs_data)
    # We can, of course, do selective indexing to avoid realizing ALL the underlying data to memory
    assert torch.allclose(src[10:15], mrcs_data[10:15])


def test_loading_starfile(mrcs_data):
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections_13.star"),
        datadir=pytest.DATADIR,
    )
    arr = src[7:12]
    assert arr.shape == (5, 30, 30)


def test_loading_txtfile(mrcs_data):
    src = ImageSource.from_file(os.path.join(pytest.DATADIR, "toy_projections_2.txt"))
    # Each line of the txt file points to an .mrcs file with 1000 particles. Try to get a slice across the two.
    arr = src[990:1005]
    assert arr.shape == (15, 30, 30)
    assert torch.allclose(arr[:10], mrcs_data[-10:])
    assert torch.allclose(arr[10:], mrcs_data[:5])


def test_loading_csfile(mrcs_data):
    src = ImageSource.from_file(os.path.join(pytest.DATADIR, "empiar_10076_7.cs"))
    arr = src[:]
    assert arr.shape == (7, 320, 320)
    starfile_data = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "empiar_10076_7.star"),
        datadir=pytest.DATADIR,
        lazy=False,
    )[:]

    assert torch.allclose(arr, starfile_data)


@pytest.mark.parametrize(
    "particles", ["toy.mrcs", "toy.star", "toy.txt"], indirect=True
)
@pytest.mark.parametrize("indices", [None, np.arange(101, 203)])
@pytest.mark.parametrize("chunksize", [100, 300, 999])
@pytest.mark.parametrize(
    "transform_fn", [lambda x, i: x, lambda x, i: -x], ids=["none", "invert"]
)
def test_write_mrc(tmpdir, particles, indices, chunksize, transform_fn):
    src = ImageSource.from_file(particles.path, indices=indices)
    out_fl = os.path.join(tmpdir, "out.mrc")
    src.write_mrc(out_fl, chunksize=chunksize, transform_fn=transform_fn)
    new_src = ImageSource.from_file(out_fl)
    assert isinstance(new_src, MRCFileSource)
    assert np.allclose(src.images(), transform_fn(new_src.images(), None))


@pytest.mark.parametrize(
    "particles", ["toy.mrcs", "toy.star", "toy.txt"], indirect=True
)
@pytest.mark.parametrize("chunksize", [100, 300, 999])
def test_source_iteration(particles, chunksize):
    # An ImageSource can be iterated over, with an optional chunksize (default 1000)
    # 999 is tested because numoy/torch operations often have edge cases when chunksize
    # is 1 (number of images is 1000)
    src = ImageSource.from_file(particles.path)
    chunk_sizes = []
    for i, (indices, chunk) in enumerate(src.chunks(chunksize=chunksize)):
        assert isinstance(chunk, torch.Tensor)
        assert chunk.ndim == 3
        chunk_sizes.append(chunk.shape[0])

    # chunk sizes will be (300, L, L) in shape...
    assert all(chunk_sizes[i] == chunksize for i in range(len(chunk_sizes) - 1))
    # ...except the last iteration which gets the left-over images
    assert chunk_sizes[-1] == (src.n % chunksize) or chunksize


def test_prespecified_indices(mrcs_data):
    # An ImageSource can have pre-specified indices, which will be the only ones used when reading underlying data.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections.mrcs"),
        indices=np.array([0, 1, 5, 304]),
    )
    assert src.shape == (4, 30, 30)  # Not (100, 30, 30)

    # Once read, caller-side indexing can be done as usual (i.e. going from 0 to src.n),
    # and we can forget about what indices were originally passed in.
    data = src.images(np.array([2, 3]))

    assert torch.allclose(mrcs_data[np.array([5, 304]), :, :], data)


def test_prespecified_indices_eager(mrcs_data):
    # An ImageSource can have pre-specified indices, which will be the only ones used when reading underlying data.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections.mrcs"),
        indices=np.array([0, 1, 5, 304]),
        lazy=False,
    )
    assert src.shape == (4, 30, 30)  # Not (100, 30, 30)

    # Once read, caller-side indexing can be done as usual (i.e. going from 0 to src.n),
    # and we can forget about what indices were originally passed in.
    data = src.images(np.array([2, 3]))
    assert torch.allclose(mrcs_data[np.array([5, 304]), :, :], data)


def test_txt_prespecified_indices(mrcs_data):
    # Each line of the txt file points to an .mrcs file with 1000 particles.
    # Specify indices that span these files.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections_2.txt"),
        indices=np.array([35, 631, 1531, 363, 1693, 1875]),
    )
    assert src.shape == (6, 30, 30)  # Not (100, 30, 30)

    # Once read, caller-side indexing can be done as usual (i.e. going from 0 to src.n),
    # and we can forget about what indices were originally passed in.
    data = src.images(np.array([2, 3, 5, 0, 1, 4]))

    assert torch.allclose(
        mrcs_data[np.array([531, 363, 875, 35, 631, 693]), :, :], data
    )


def test_txt_prespecified_indices_contiguous(mrcs_data):
    # Each line of the txt file points to an .mrcs file with 1000 particles.
    # Specify indices that span these files.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections_2.txt"),
        indices=np.array([35, 1034, 1032, 1033, 42, 36]),
    )
    assert src.shape == (6, 30, 30)  # Not (100, 30, 30)

    # Note that we end up accessing contiguous memory locations
    # since the indexing below ends up being interpreted as
    # [1032, 1033, 1034, 35, 36]
    # and the 2 .mrcs files (indices <1000 and indices >=1000) are identical
    data = src.images(np.array([2, 3, 1, 0, 5]), require_contiguous=True)

    assert torch.allclose(mrcs_data[np.array([32, 33, 34, 35, 36]), :, :], data)


def test_txt_prespecified_indices_contiguous_eager(mrcs_data):
    # Each line of the txt file points to an .mrcs file with 1000 particles.
    # Specify indices that span these files.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections_2.txt"),
        indices=np.array([35, 1034, 1032, 1033, 42, 36]),
        lazy=False,
    )
    assert src.shape == (6, 30, 30)  # Not (100, 30, 30)

    # Note that we end up accessing contiguous memory locations
    # since the indexing below ends up being interpreted as
    # [1032, 1033, 1034, 35, 36]
    # and the 2 .mrcs files (indices <1000 and indices >=1000) are identical
    data = src.images(np.array([2, 3, 1, 0, 5]), require_contiguous=True)

    assert torch.allclose(mrcs_data[np.array([32, 33, 34, 35, 36]), :, :], data)


def test_txt_prespecified_indices_eager(mrcs_data):
    # Each line of the txt file points to an .mrcs file with 1000 particles.
    # Specify indices that span these files.
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections_2.txt"),
        indices=np.array([35, 631, 1531, 363, 1693, 1875]),
        lazy=False,
    )
    assert src.shape == (6, 30, 30)  # Not (100, 30, 30)

    # Once read, caller-side indexing can be done as usual (i.e. going from 0 to src.n),
    # and we can forget about what indices were originally passed in.
    data = src.images(np.array([2, 3, 5, 0, 1, 4]))

    assert torch.allclose(
        mrcs_data[np.array([531, 363, 875, 35, 631, 693]), :, :], data
    )


def test_prespecified_indices_chunked(mrcs_data):
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections.mrcs"),
        indices=np.array([0, 1, 5, 304]),
    )
    assert src.shape == (4, 30, 30)  # Not (1000, 30, 30)

    for i, (indx, chunk) in enumerate(src.chunks(chunksize=2)):
        assert len(indx) == chunk.shape[0]
        if i == 0:
            assert torch.allclose(mrcs_data[np.array([0, 1]), :, :], chunk)
        elif i == 1:
            assert torch.allclose(mrcs_data[np.array([5, 304]), :, :], chunk)


def test_prespecified_indices_eager_chunked(mrcs_data):
    src = ImageSource.from_file(
        os.path.join(pytest.DATADIR, "toy_projections.mrcs"),
        indices=np.array([0, 1, 5, 304]),
        lazy=False,
    )
    assert src.shape == (4, 30, 30)  # Not (100, 30, 30)

    for i, (indices, chunk) in enumerate(src.chunks(chunksize=2)):
        assert len(indices) == chunk.shape[0]
        if i == 0:
            assert torch.allclose(mrcs_data[np.array([0, 1]), :, :], chunk)
        elif i == 1:
            assert torch.allclose(mrcs_data[np.array([5, 304]), :, :], chunk)
