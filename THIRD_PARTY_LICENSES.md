# Third-party software

Asset Studio is an independent interface. Infinigen is a separate project by
Princeton Vision & Learning Lab. This is not an official Princeton UI and does
not imply endorsement.

The release ZIP contains original integration code and small original schemas;
it does not contain Infinigen, Blender, Python runtimes or their dependencies.
The managed installer retains upstream `LICENSE` files in downloaded sources.

| Dependency | Pinned source | License / notices |
| --- | --- | --- |
| Infinigen | [Princeton repository](https://github.com/princeton-vl/infinigen/tree/01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c), 1.19.0 | [BSD-3-Clause](https://github.com/princeton-vl/infinigen/blob/01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c/LICENSE), Copyright (C) 2023 Princeton University |
| infinigen_gpl | [10c1d76](https://github.com/princeton-vl/infinigen_gpl/tree/10c1d76f5c35003e919be7265185c9c355e3b70c) | [GPL version 3 license](https://github.com/princeton-vl/infinigen_gpl/blob/10c1d76f5c35003e919be7265185c9c355e3b70c/LICENSE); see individual file notices |
| OcMesher | [bb895a0](https://github.com/princeton-vl/OcMesher/tree/bb895a01b8f574da10be1df470210df7463a75c7) | BSD-3-Clause, Copyright (c) 2023 Princeton Vision & Learning Lab; preserved LICENSE |
| GLM headers | [cc98465](https://github.com/g-truc/glm/tree/cc98465e3508535ba8c7f6208df934c156a018dc) | [MIT / Happy Bunny](https://github.com/g-truc/glm/blob/cc98465e3508535ba8c7f6208df934c156a018dc/copying.txt) |
| Blender / bpy | [Blender](https://www.blender.org/about/license/) 4.2.0 | GNU GPL; Python API and module retain Blender notices |
| Miniconda bootstrap | [Official Anaconda archive](https://repo.anaconda.com/miniconda/) py311 24.11.1-0 | Installer and included packages retain their licenses; no runtime is redistributed in our ZIP |

Python dependencies are resolved into the isolated environment from PyPI using
the pinned project's metadata and our compatibility constraints. Their package
license metadata remains in that environment. Inspect it before redistributing
an environment or generated content that includes third-party resources.

CUDA and OptiX availability refers to devices reported by the worker's Blender
Cycles runtime. Asset Studio does not distribute NVIDIA drivers or SDKs.
