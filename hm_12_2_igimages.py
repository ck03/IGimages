from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
import time
import json
import requests
import os
from pymongo import MongoClient
from copy import deepcopy
import datetime as dt


class IGImagesSpider:
    def __init__(self, cname, ename, today, url):
        chrome_options = Options()
        # 沒有這一行會自動開啟瀏覽器
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(chrome_options=chrome_options,
                                       executable_path=r'D:\Study\Python2\chromedriver\chromedriver.exe')
        self.cname = cname
        self.ename = ename
        self.url = url
        self.result_list = []
        self.result_list_json = []
        self.result_dict = {}
        self.temp_id = []
        self.headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36"}
        self.client = MongoClient(host="127.0.0.1", port=27017)
        self.collection = self.client["igimg"]["imginfo"]
        self.dbid_list = []
        self.today = today
        self.webposts = 0
        self.webpoststemp = 0

    # 解析id
    def parser_str(self, sid):
        id = str(sid).split("/")
        id = id[-2]
        return id

    # 下載圖片
    def downloadimg(self, url, folder_path, sid):
        res = requests.get(url, headers=self.headers)
        # 下載圖片到本地去
        with open(folder_path + "{}_{}.jpg".format(self.cname, sid), "wb") as f:
            f.write(res.content)

    def get_content_list(self, folder_path):
        wait = WebDriverWait(self.driver, 2)
        while True:
            # 找是否有row
            div_list = self.driver.find_elements_by_xpath("//div[@class=' _2z6nI']/article/div[1]/div/div")
            print(len(div_list))

            if len(div_list) > 0:
                # row
                icount = 0
                realcount = 0
                for div in div_list:
                    # 每一row 有 3 個 column(即3張)
                    div_col = div.find_elements_by_xpath("./div[@class='v1Nh3 kIKUG  _bz0w']")
                    # print("div_col=", len(div_col))
                    sid_list = []
                    icount = 0
                    for col in div_col:
                        realcount += 1
                        item = {}
                        sid = col.find_element_by_xpath("./a").get_attribute("href")
                        sid = self.parser_str(sid)
                        item["id"] = sid
                        item["cname"] = self.cname
                        item["ename"] = self.ename
                        item["date"] = self.today
                        sid_list.append(sid)
                        # 因為滾動後會加載div,但要判斷已下載過的id就不再下載了
                        set1 = set(self.temp_id)
                        set2 = set(sid_list)
                        set6 = set2.difference(set1)
                        # len(set6)>0表示有新的id所以要下載
                        if len(set6) > 0:
                            item["imgurl"] = col.find_element_by_xpath("./a/div[1]/div[1]/img").get_attribute("src")
                            # 跟 self.dbid_list 比對 , 沒有在self.dbid_list裡面的才要insert
                            setdb = set(self.dbid_list)
                            setweb = set(list([sid]))
                            setdiff = setweb.difference(setdb)
                            if len(setdiff) > 0:
                                # 馬上下載圖片
                                self.downloadimg(item["imgurl"], folder_path, item["id"])
                                # print(item)
                                self.result_list.append(item)
                                self.result_list_json.append(deepcopy(item))
                                # 下載到DB
                                self.collection.insert_one(item)
                                self.webposts -= 1
                                if self.webposts % 30 == 0:
                                    if self.webposts != 0:
                                        print("還剩{}張".format(self.webposts))
                                    else:
                                        print("已全部下載完畢....")
                            self.temp_id.append(sid)
                            icount += 1

                print("icount=", icount)
                # 已經找過的圖片張數 > 本次真的要下載張數的10倍就不再找了,加快速度
                # 此段mark則會再全部掃一遍
                if realcount > self.webpoststemp * 10:
                    break
                if icount == 0:
                    break
                # 當區塊的row找完後將游標定位在最後一列
                # 拖動到可见的元素去, 因為它是滾動頁面往下,所以此動作是在模擬頁面往下移到目前最後一個元素,代表頁面在滾動
                self.driver.execute_script('arguments[0].scrollIntoView();', div_list[-1])
                time.sleep(5)
                # # 找是否有row
                # div_list = self.driver.find_elements_by_xpath("//div[@class=' _2z6nI']/article/div[1]/div/div")
                # print(len(div_list))
            else:
                break

    # mongodb跟網頁的數字比對,看是否有增加的圖片
    def diffposts(self):
        # 現在貼文總數
        webposts = self.driver.find_element_by_xpath("//section[@class='zwlfE']/ul/li[1]").text
        webposts = "".join(webposts)
        webposts = int(webposts.split(" ")[0].replace(",", ""))

        # print(webposts)
        dbposts = self.collection.find({"ename": "{}".format(self.ename)})
        # print(dbposts.count())
        # 只有網頁的總貼文大於DB裡的貼文才需要下載
        # 可是要是IG刪掉圖片比新增的還多,則會有盲點,要注意此段是否需要變化
        # 因為比如我已下載100張了,但明天它有刪掉10張另外增加5張,則本次爬蟲不會跑.
        if webposts > dbposts.count():
            self.webposts = webposts - dbposts.count()
            self.webpoststemp = self.webposts
            # 記錄db裡的id欄位以供後序比對
            if dbposts.count() > 0:
                for sid in dbposts:
                    self.dbid_list.append(sid["id"])
            return True
        else:
            return False

    def run(self):
        print("IG爬蟲開始.....")
        # 1.取得url
        self.driver.get(self.url)
        bolnext = self.diffposts()
        # print(self.dbid_list)
        # return
        if bolnext:
            # 檢查目錄是否存在
            folder_path = "IG_{}/".format(self.cname)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

            # 2.獲取響應,取得資料
            self.get_content_list(folder_path)

            # 3.保存
            self.result_dict["result"] = self.result_list_json
            with open("{}_img_{}.json".format(self.cname, self.today), "w", encoding="utf-8") as f:
                f.write(json.dumps(self.result_dict, ensure_ascii=False, indent=2))

        self.driver.close()
        self.driver.quit()
        print("IG爬蟲結束.....")


if __name__ == "__main__":
    """
        name:中文名字
        cname:英文名字
        url: IG下載網址
    """
    today = dt.date.today()
    today = str(today)
    today = today.replace("-", "")
    igimagesspider = IGImagesSpider("name", "cname", today, "url")
    igimagesspider.run()