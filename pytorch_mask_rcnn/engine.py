import sys
import time
import torch

from .utils import Meter, TextArea
try:
    from .datasets.xylem_eval import XylemEvaluator, prepare_for_xylem_coco
except:
    pass


def train_one_epoch(model, optimizer, data_loader, device, epoch, args):
    for p in optimizer.param_groups:
        p["lr"] = args.lr_epoch
    # args.iter < 0이면 전체 데이터셋을 학습
    iters = len(data_loader) if args.iters < 0 else args.iters

    t_m = Meter("total")
    m_m = Meter("model")
    b_m = Meter("backward")
    model.train()
    A = time.time()
    for i, (image, target) in enumerate(data_loader):
        T = time.time()
        num_iters = epoch * len(data_loader) + i
        # 안정적인 학습 보조 warmup_iter
        if num_iters <= args.warmup_iters:
            r = num_iters / args.warmup_iters
            for j, p in enumerate(optimizer.param_groups):
                p["lr"] = r * args.lr_epoch
                   
        image = image.to(device)
        target = {k: v.to(device) for k, v in target.items()}
        S = time.time()
        
        losses = model(image, target)
        total_loss = sum(losses.values())
        m_m.update(time.time() - S)
        
        S = time.time()
        total_loss.backward()
        b_m.update(time.time() - S)
        
        optimizer.step()
        optimizer.zero_grad()
        
        #@ add True for debugging
        if num_iters % args.print_freq == 0 or True:
            print("{}\t".format(num_iters), "\t".join("{:.3f}".format(l.item()) for l in losses.values()))
        
        t_m.update(time.time() - T)
        if i >= iters - 1:
            break
           
    A = time.time() - A
    print("iter: {:.1f}, total: {:.1f}, model: {:.1f}, backward: {:.1f}".format(1000*A/iters,1000*t_m.avg,1000*m_m.avg,1000*b_m.avg))
    return A / iters
            

def evaluate(model, data_loader, device, args, generate=True):
    iter_eval = None
    if generate:
        iter_eval = generate_results(model, data_loader, device, args)
    
    dataset = data_loader #
    iou_types = ["bbox", "segm"]
    #@ CocoEvaluator to XylemEvaluator(from xylem_eval.py)
    coco_evaluator = XylemEvaluator(dataset.coco, iou_types)
    results = torch.load(args.results, map_location="cpu")
    S = time.time()
    coco_evaluator.accumulate(results)
    print("accumulate: {:.1f}s".format(time.time() - S))
    # collect outputs of buildin function print
    temp = sys.stdout
    sys.stdout = TextArea()
    coco_evaluator.summarize()
    output = sys.stdout
    sys.stdout = temp
    
    # 명시적으로 output.get_AP() 호출하여 AP 값 계산
    ap_values = output.get_AP()
    print(ap_values)  # AP 값 출력
        
    return output, iter_eval, ap_values  # ap_values도 함께 반환
    
    
# generate results file   
@torch.no_grad()   
def generate_results(model, data_loader, device, args):
    iters = len(data_loader) if args.iters < 0 else args.iters
        
    t_m = Meter("total")
    m_m = Meter("model")
    coco_results = []
    model.eval()
    A = time.time()
    for i, (image, target) in enumerate(data_loader):
        T = time.time()
        
        image = image.to(device)
        target = {k: v.to(device) for k, v in target.items()}

        S = time.time()
        #torch.cuda.synchronize()
        output = model(image)
        m_m.update(time.time() - S)
        
        prediction = {target["image_id"].item(): {k: v.cpu() for k, v in output.items()}}
        #@ prepare_for_coco to prepare_for_xylem_coco(from xylem_eval.py)
        coco_results.extend(prepare_for_xylem_coco(prediction))

        t_m.update(time.time() - T)
        if i >= iters - 1:
            break
     
    A = time.time() - A 
    print("iter: {:.1f}, total: {:.1f}, model: {:.1f}".format(1000*A/iters,1000*t_m.avg,1000*m_m.avg))
    torch.save(coco_results, args.results)
        
    return A / iters
