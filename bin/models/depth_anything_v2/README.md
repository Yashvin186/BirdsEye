# Depth Anything V2 Model Weights

Place the ONNX model weights file here:
`bin/models/depth_anything_v2/model.onnx`

### Download Options:
You can download the Depth Anything V2 Small (or Base) ONNX model:
- Model format: ONNX (opset 14+)
- Expected file name: `model.onnx`
- Input: `[1, 3, 518, 518]` (Image RGB normalized with ImageNet mean/std)
- Output: `[1, 518, 518]` (Predicted relative metric depth)

