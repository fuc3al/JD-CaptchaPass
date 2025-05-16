'''
Author: Fucal
LastEditTime: 2025-5-2
Description:        
                *		Mahiro
Copyright (c) 2024-2025 by Fucal, All Rights Reserved. 
'''

import sys
import requests
import json
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, Locator, ElementHandle 

from .logger import get_logger
LOG = get_logger()

bing_api_post_url = "http://www.bingtop.com/ocr/upload/"
bing_username = "None"
bing_password = "None"
#手动填写账号信息，验证码识别服务
class Captcha:
    def __init__(self, page=None):
        self.page = page  # 添加双下划线使其成为私有属性
        self.verify_status = False  # 验证状态标记

    def click(self):
        verify_button = self.page.wait_for_selector('.verifyBtn')
        verify_button.click()
        self.solve()
        return self.verify_status
    
    def solve(self):
        # 等待验证码模态框出现
        self.page.wait_for_timeout(2000)
        modal = self.page.wait_for_selector('#captcha_modal')
        # 获取模态框的 class 属性
        modal_class = modal.get_attribute('class')

        try:
            if 'captcha_modal_smart' in modal_class:
                LOG.info("检测到智能验证码版本")
                return self.coordinates()            
            if 'captcha_modal_radius' in modal_class:
                    LOG.info("检测到普通验证码版本")
                    return self.sliding() 
            else:
                LOG.warning("未知的验证码版本，请联系作者适配")
                sys.exit()
        except PlaywrightTimeoutError:
            pass

    #滑动型验证码
    def sliding(self):
        if(bing_username == "None" or bing_password == "None"):
            LOG.error("请填写账号信息")
            sys.exit()       
        try:
            # 1. 获取验证码和题目base64编码
            slide_img  = self.page.wait_for_selector('#small_img')
            slide_base64 = slide_img.get_attribute('src').split(',')[1]# 从src属性中提取base64数据

            background_img = self.page.wait_for_selector('#cpc_img')
            background_base64 = background_img.get_attribute('src').split(',')[1]

            # 2. 调用打码平台
            params = {
                "username": "%s" % bing_username,
                "password": "%s" % bing_password,
                "captchaData": background_base64,
                "subCaptchaData": slide_base64,
                "captchaType": 1316
            }

            response = requests.post(bing_api_post_url, data=params)
            dictdata = json.loads(response.text)  # 先将响应转换为字典

            if dictdata['code'] == 0:  # 请求成功
                recognition = dictdata['data']['recognition']  # 获取recognition字符串 "131,58"
                distance = int(recognition.split(',')[0])  # 分割字符串并获取第一个值
                LOG.info(f"识别成功，滑动距离: {distance}")
                self._slide_sliding(distance)  # 调用滑动函数
            else:
                LOG.error(f"识别失败: {dictdata['msg']}")
                LOG.error("刷新题目")
                return self.solve

        except Exception as e:
            LOG.error(f"答案处理失败: {e}")
            LOG.error("如果反复失败，联系作者适配")
            return self.solve
    
    def _slide_sliding(self, distance: int):
        """
        执行滑块拖动操作。
        包含重试逻辑：如果失败，会调用 self.solve()。
        """
        self.current_attempt_distance = distance # 保存当前尝试的距离，以便 solve() 重试时可能用到

        try:
            slider = self.page.wait_for_selector('.move-img', timeout=800)
            if not slider:
                LOG.error("未找到滑块元素")
                return self.solve() # 重试逻辑

            box = slider.bounding_box()
            if not box:
                LOG.error("无法获取滑块元素的边界框")
                return self.solve() # 重试逻辑

            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2

            self.page.mouse.move(start_x, start_y, steps=random.randint(2, 4))
            self.page.mouse.down()
            self.page.wait_for_timeout(random.randint(10, 25))

            current_x_abs = start_x # 使用绝对坐标来跟踪 mouse.move 的目标位置
            
            tracks = self.get_track_extreme_fast_v2(distance) 

            estimated_total_duration_ms = 0
            for item in tracks:
                if isinstance(item, (int, float)):
                    estimated_total_duration_ms += item
                else:
                    _, _, steps = item
                    estimated_total_duration_ms += steps * 11 
            LOG.info(f"生成轨迹 {len(tracks)} 段。预估鼠标操作时长: {estimated_total_duration_ms / 1000:.3f} 秒")

            for i, item in enumerate(tracks):
                if isinstance(item, (int, float)):
                    self.page.wait_for_timeout(item)
                    continue

                x_offset, y_offset, steps_for_segment = item
                # target_x_abs 是绝对屏幕坐标
                target_x_abs = current_x_abs + x_offset # x_offset 是相对上一点的位移
                target_y_abs = start_y + y_offset 

                self.page.mouse.move(target_x_abs, target_y_abs, steps=steps_for_segment)
                current_x_abs = target_x_abs # 更新当前鼠标的绝对X轴位置
            
            actual_moved_x = current_x_abs - start_x
            LOG.info(f"滑动动作完成。目标距离: {distance}, 实际总X位移: {actual_moved_x:.2f}")

            self.page.wait_for_timeout(random.randint(15, 30))
            self.page.mouse.up()

            self.page.wait_for_timeout(random.randint(350, 450))

            modal = self.page.query_selector('#captcha_modal')
            success_element = self.page.query_selector('.verification-success')
            failure_element = self.page.query_selector('.verification-error')

            #等待页面加载完成
            self.page.wait_for_timeout(2000)

            if success_element and success_element.is_visible():
                LOG.success("验证通过！(检测到成功元素)")
                self.verify_status = True
            elif modal and modal.is_visible():
                LOG.warning("验证未通过 (验证码弹窗仍在)，尝试重试...")
                return self.solve() 
            elif failure_element and failure_element.is_visible():
                LOG.warning("验证未通过 (检测到失败元素)，尝试重试...")
                return self.solve()
            else:
                slider_still_present = self.page.query_selector('.move-img')
                if not slider_still_present or not slider_still_present.is_visible():
                    LOG.success("验证通过！(滑块消失或不再可见)")
                    self.verify_status = True
                else:
                    LOG.warning("验证结果不明确 (滑块仍在)，可能未通过，尝试重试...")
                    return self.solve()

        except PlaywrightTimeoutError:
            LOG.error("验证码处理超时 (例如等待元素)")
            return self.solve()
        except Exception as e:
            LOG.error(f"滑动验证码过程中发生未知异常: {e}")
            # import traceback
            # LOG.error(traceback.format_exc())
            return self.solve()

    def get_track_extreme_fast_v2(self, distance: int):
        """
        生成一个极速的轨迹：大幅过冲（非线性加速感），明显停顿后快速拉回。
        返回: 轨迹列表，包含 (x_offset, y_offset, steps) 或暂停毫秒数。
        x_offset 是相对于上一个点的位移。
        """
        tracks = []
        current_x_relative_offset = 0.0 # 记录相对于起点的总偏移，用于计算校正距离

        # --- 阶段1: 极速过冲 (Flick) ---
        flick_duration_target = random.uniform(0.12, 0.18) # 过冲阶段目标时长 (秒) - 进一步压缩
        flick_overshoot_factor = random.uniform(0.25, 0.40) # 过冲量 (25%-40%)
        flick_target_total_offset = distance * (1.0 + flick_overshoot_factor)
        
        # 非线性加速感通过分段位移比例实现
        # 将过冲分为3-4段
        num_flick_segments = random.choice([3, 4])
        # 预设每段位移占总过冲位移的比例（模拟非线性加速）
        # 例如3段: [0.2, 0.5, 0.3] -> 初始小，中间大，最后收尾
        # 例如4段: [0.1, 0.4, 0.3, 0.2]
        if num_flick_segments == 3:
            segment_ratios = [random.uniform(0.15,0.25), random.uniform(0.45,0.60), 0.0] # 第三个动态计算
            segment_ratios[2] = 1.0 - segment_ratios[0] - segment_ratios[1]
        else: # 4 segments
            segment_ratios = [random.uniform(0.1,0.15), random.uniform(0.35,0.45), random.uniform(0.25,0.35), 0.0]
            segment_ratios[3] = 1.0 - sum(segment_ratios[:3])
        
        # 确保 ratios 和为1且不为负
        if any(r <= 0 for r in segment_ratios): # 简单修正，实际应用中可能需要更鲁棒的分配
            segment_ratios = [1.0/num_flick_segments] * num_flick_segments


        # 每步约11毫秒，计算总步数
        total_flick_steps = max(num_flick_segments, int(flick_duration_target / 0.011)) 
        
        LOG.info(f"急速过冲阶段: 目标总偏移={flick_target_total_offset:.2f}px, 预计时长={flick_duration_target:.3f}s, 总步数={total_flick_steps}, 分{num_flick_segments}段")
        
        remaining_total_flick_steps = total_flick_steps
        for i in range(num_flick_segments):
            segment_distance = flick_target_total_offset * segment_ratios[i]
            
            # 分配步数：可以按时间比例，或者简单均分后随机调整
            if i == num_flick_segments - 1: # 最后一段用完剩余步数
                segment_steps = max(1, remaining_total_flick_steps)
            else:
                # 非线性加速感：初始段步数少（显得快），中间段步数可略多或仍少
                if i == 0 : # 第一段，极快
                    segment_steps = max(1, int(total_flick_steps * (flick_duration_target *0.15 / flick_duration_target) / 0.011 )) # 占总时长15%的步数
                    segment_steps = max(1, min(segment_steps, remaining_total_flick_steps - (num_flick_segments - 1 - i) )) # 确保后续段至少有1步
                elif i < num_flick_segments -1 : # 中间段
                    segment_steps = max(1, int(total_flick_steps * (flick_duration_target *0.35 / flick_duration_target) /0.011 ) )
                    segment_steps = max(1, min(segment_steps, remaining_total_flick_steps - (num_flick_segments - 1 - i) ))
                else: # should not happen due to first if
                    segment_steps = max(1, remaining_total_flick_steps)
            
            segment_steps = max(1, min(segment_steps, remaining_total_flick_steps))


            s_y_flick = random.uniform(-2.5, 2.5) # 过冲时Y轴抖动
            tracks.append((round(segment_distance, 2), round(s_y_flick, 2), segment_steps))
            
            current_x_relative_offset += segment_distance
            remaining_total_flick_steps -= segment_steps
            if remaining_total_flick_steps < 0: remaining_total_flick_steps = 0

        # --- 阶段1.5: 回弹前明显停顿 ---
        pause_before_rebound = random.randint(90, 180) # 停顿 90-180 毫秒
        tracks.append(pause_before_rebound)
        LOG.info(f"过冲后，回弹前停顿: {pause_before_rebound}ms")

        # --- 阶段2: 快速校正 (Correction) ---
        correction_duration_target = random.uniform(0.07, 0.11) # 校正阶段目标时长 (秒)
        
        correction_needed_x = distance - current_x_relative_offset 
        
        num_correction_moves = random.randint(1, 2)
        total_correction_steps = max(num_correction_moves, int(correction_duration_target / 0.011))

        LOG.info(f"快速校正阶段: 需校正={correction_needed_x:.2f}px, 预计时长={correction_duration_target:.3f}s, 总步数={total_correction_steps}, 分{num_correction_moves}段")

        remaining_correction_dist = correction_needed_x
        remaining_correction_steps = total_correction_steps
        
        for i in range(num_correction_moves):
            if abs(remaining_correction_dist) < 0.05: break 

            is_last_correction_move = (i == num_correction_moves - 1)
            
            current_move_dist = remaining_correction_dist if is_last_correction_move else (remaining_correction_dist / (num_correction_moves - i) * random.uniform(0.8,1.2))
            current_move_steps = remaining_correction_steps if is_last_correction_move else max(1, remaining_correction_steps // (num_correction_moves - i))
            current_move_steps = max(1, min(current_move_steps, remaining_correction_steps))


            s_y_correction = random.uniform(-0.5, 0.5)
            tracks.append((round(current_move_dist, 2), round(s_y_correction, 2), current_move_steps))

            current_x_relative_offset += current_move_dist
            remaining_correction_dist -= current_move_dist
            remaining_correction_steps -= current_move_steps
            if remaining_correction_steps <0: remaining_correction_steps = 0
        
        LOG.info(f"轨迹生成完毕。最终计算出的相对X偏移: {current_x_relative_offset:.2f} (目标是 {distance})")
        return tracks
    #点击型验证码
    def coordinates(self):
        if(bing_username == "None" or bing_password == "None"):
            LOG.error("请填写账号信息")
            sys.exit()       
        try:
            # 1. 获取验证码和题目base64编码
            captcha_img = self.page.wait_for_selector('#cpc_img')
            captcha_base64 = captcha_img.get_attribute('src').split(',')[1]# 从src属性中提取base64数据

            hint_img = self.page.wait_for_selector('div.tip img')
            hint_base64 = hint_img.get_attribute('src').split(',')[1]

            # 2. 调用打码平台
            params = {
                "username": "%s" % bing_username,
                "password": "%s" % bing_password,
                "captchaData": captcha_base64,
                "subCaptchaData": hint_base64,
                "captchaType": 1306
            }
            response = requests.post(bing_api_post_url, data=params)
            dictdata=json.loads(response.text)

            # 3. 解析结果
            if dictdata['code'] == 0:
                coord_str = dictdata['data']['recognition']# 获取坐标字符串
                LOG.info(f"识别成功，答案坐标: {coord_str}")
            else:
                LOG.error(f"识别失败: {response['msg']}")
                LOG.error("刷新题目")
                return self.solve

            # 解析坐标字符串为列表
            coord_list = []
            for coord in coord_str.split('|'):
                x, y = map(int, coord.split(','))
                coord_list.append([x, y])
                
            self._click_coordinates(coord_list)# 传递解析后的坐标列表
                
        except Exception as e:
            LOG.error(f"答案处理失败: {e}")
            LOG.error("如果反复失败，联系作者适配")
            return self.solve
#等待刷新新的题目，目前观测是，只会刷新同一类型题目
#如果后续有问题，在进行更新
    def _click_coordinates(self, coord_list):
        try:
            verify_img = self.page.wait_for_selector('#cpc_img')
            box = verify_img.bounding_box()
                
            # 点击每个坐标点
            for x, y in coord_list:
                actual_x = box['x'] + x
                actual_y = box['y'] + y
                self.page.mouse.click(actual_x, actual_y)                   
                self.page.wait_for_timeout(500)  # 等待点击动画
            
            submit_btn = self.page.wait_for_selector('#submit-btn')
            submit_btn.click()

            try:
                self.page.wait_for_timeout(2000)  # 等待验证结果
                modal = self.page.query_selector('#captcha_modal')
                if modal and modal.is_visible():
                    LOG.warning("验证未通过，重试中...")
                    return self.solve()
                
                LOG.success("验证通过！")
                self.verify_status = True
            
            except PlaywrightTimeoutError:
                LOG.error("验证码处理超时")
                LOG.error("如果反复失败，联系作者适配")
                return self.solve()    
                                
        except Exception as e:
            LOG.error(f"点击验证码失败: {e}")
            LOG.error("如果反复失败，联系作者适配")
            return self.solve
