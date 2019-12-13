pragma solidity ^0.4.21;

contract SmartContract8 {
    // 应收款项
    struct Receivable {
        uint id;
        uint amount;
        uint payableId;
        address payer;
        uint dueDate;
    }

    // 应付款项
    struct Payable {
        uint id;
        uint amount;
        uint receivableId;
        address receiver;
        uint dueDate;
    }

    // 货物
    struct Inventory {
        string name;
        address owner;
        uint amount;
        uint price;
        bool onsale;
    }

    // 公司/机构
    struct Company {
        address addr;
        string name;
        uint credit;
        uint balance;
        string status;
        Receivable[] receivables;
        Payable[] payables;
        mapping (string => Inventory) inventories;
    }

    // 映射表
    mapping (address => Company) public companies;

    // 有权发行货币
    address[] public banks;

    event Issued(address to, uint amount);
    event CreditIssued(address to, uint amount);
    event Sold(address buyer, address seller, string sku, uint amount, address payer, address receiver, uint payableId, uint receivableId);
    event Received(address payer, address receiver, uint amount, uint payableId, uint receivableId);
    event Transferred(address from, address to, uint amount);
    event ReceivableTransferred(address from, address to, uint amount, uint fromReceivableId, uint toReceivableId, bool discount);
    event NewCompany(address addr, string name);
    event NewBank(address addr);
    event NewInventory(address seller, string sku, string name, uint amount, uint price);

    event PayableQuery(address addr, uint amount);
    event ReceivableQuery(address addr, uint amount);

    constructor() public {
        banks.push(msg.sender);
    }

    // 获取货物详情
    function getInvetory(address seller, string sku) public view returns (string, address, uint, uint, bool) {
        Company storage sellerCompany = companies[seller];
        Inventory storage inventory = sellerCompany.inventories[sku];
        return (inventory.name, inventory.owner, inventory.amount, inventory.price, inventory.onsale);
    }

    // 获取应收账款
    function getReceivable(uint id) public view returns (uint, uint, uint, address, uint) {
        Company storage company = companies[msg.sender];
        Receivable storage receivable = company.receivables[id];
        return (receivable.id, receivable.amount, receivable.payableId, receivable.payer, receivable.dueDate);
    }

    // 获取应付账款
    function getPayable(uint id) public view returns (uint, uint, uint, address, uint) {
        Company storage company = companies[msg.sender];
        Payable storage _payable = company.payables[id];
        return (_payable.id, _payable.amount, _payable.receivableId, _payable.receiver, _payable.dueDate);
    }

    
    // 获取公司应付账款总额
    function totalPayable(address addr) public returns (uint) {
        uint total = 0;
        for (uint i = 0; i < companies[addr].payables.length; ++i) {
            total += companies[addr].payables[i].amount;
        }

        emit PayableQuery(addr, total);
        return total;
    }

    // 获取公司应收账款总额
    function totalReceivable(address addr) public returns (uint) {
        uint total = 0;
        for (uint i = 0; i < companies[addr].receivables.length; ++i) {
            total += companies[addr].receivables[i].amount;
        }

        emit ReceivableQuery(addr, total);
        return total;
    }

    // 注册公司
    function registerCompany(string name) public {
        Company storage company = companies[msg.sender];
        company.addr = msg.sender;
        company.name = name;
        emit NewCompany(msg.sender, name);
    }

    // 添加银行
    function addBank(address addr) public {
        for (uint i = 0; i < banks.length; ++i) {
            if (msg.sender == banks[i]) {
                banks.push(addr);
                emit NewBank(addr);
            }
        }
    }

    // 是否银行
    function isBank() public view returns (bool) {
        for (uint i = 0; i < banks.length; ++i) {
            if (msg.sender == banks[i]) {
                return true;
            }
        }
        return false;
    }

    // 发行货币
    function issue(address to, uint amount) public {
        for (uint i = 0; i < banks.length; ++i) {
            if (msg.sender == banks[i]) {
                companies[to].balance += amount;
                emit Issued(to, amount);
            }
        }
    }

    // 发行信用
    function issueCredit(address to, uint amount) public {
        for (uint i = 0; i < banks.length; ++i) {
            if (msg.sender == banks[i]) {
                companies[to].credit += amount;
                emit CreditIssued(to, amount);
            }
        }
    }

    // 添加货物
    function publishInventory(string sku, string name, uint amount, uint price) public {
        Company storage sellerCompany = companies[msg.sender];
        sellerCompany.inventories[sku] = Inventory(name, msg.sender, amount, price, true);
        emit NewInventory(msg.sender, sku, name, amount, price);
    }

    // 使用信用赊买货物
    function buy(address seller, string sku, uint amount) public {
        Company storage sellerCompany = companies[seller];
        Company storage buyerCompany = companies[msg.sender];
        Inventory storage inventory = companies[seller].inventories[sku];
        // 货物不足
        if (!inventory.onsale || inventory.amount < amount) return;
        // 信用额度不足
        if (amount * inventory.price > buyerCompany.credit) return;

        // 记录交易
        uint receivableId = sellerCompany.receivables.length;
        uint payableId = buyerCompany.payables.length;
        sellerCompany.receivables.push(
            Receivable(receivableId, amount * inventory.price, payableId, msg.sender, 0)
        );

        buyerCompany.payables.push(
            Payable(payableId, amount * inventory.price, receivableId, seller, 0)
        );

        buyerCompany.credit -= amount * inventory.price;
        companies[seller].inventories[sku].amount -= amount;

        emit Sold(msg.sender, seller, sku, amount,
        sellerCompany.receivables[receivableId].payer, buyerCompany.payables[payableId].receiver,
        payableId, receivableId);
    }

    // 用应收账款赊买
    function buyUsingReceivable(address seller, uint receivableId, string sku, uint amount) public {
        Company storage fromCompany = companies[msg.sender];
        Company storage toCompany = companies[seller];
        Inventory storage inventory = companies[seller].inventories[sku];
        Receivable storage receivable = fromCompany.receivables[receivableId];

        if (!inventory.onsale || inventory.amount < amount) return;
        if (receivable.amount < amount * inventory.price) return;

        uint toReceivableId = toCompany.receivables.length;
        toCompany.receivables.push(
            Receivable(toReceivableId, amount * inventory.price, receivable.payableId, receivable.payer, 0)
        );

        receivable.amount -= amount * inventory.price;
        companies[seller].inventories[sku].amount -= amount;

        emit ReceivableTransferred(msg.sender, seller, amount, receivableId, toReceivableId, false);
        emit Sold(msg.sender, seller, sku, amount,
        msg.sender, seller,
        receivable.payableId, toReceivableId);
    }

    // 转账
    function transfer(address to, uint amount) public {
        Company storage fromCompany = companies[msg.sender];
        Company storage toCompany = companies[to];

        if (fromCompany.balance < amount) return;

        fromCompany.balance -= amount;
        toCompany.balance += amount;

        emit Transferred(msg.sender, to, amount);
    }

    // 应收账款转移
    function transferReceivables(uint receivableId, address to, uint amount, bool discount /* 是否贴现 */) public {
        Company storage fromCompany = companies[msg.sender];
        Company storage toCompany = companies[to];
        Receivable storage receivable = fromCompany.receivables[receivableId];
        if (receivable.amount < amount) return;
        uint toReceivableId = toCompany.receivables.length;
        toCompany.receivables.push(
            Receivable(toReceivableId, amount, receivable.payableId, receivable.payer, 0)
        );

        receivable.amount -= amount;

        // 贴现的话立马转账
        if (discount) {
            fromCompany.balance += amount;
            toCompany.balance -= amount;
        }

        emit ReceivableTransferred(msg.sender, to, amount, receivableId, toReceivableId, discount);
    }



    // 应付/收账款结算
    function pay(address receiver, uint receivableId) public {
        Company storage receiveCompany = companies[receiver];
        Receivable storage receivable = receiveCompany.receivables[receivableId];
        Company storage payCompany = companies[receivable.payer];
        Payable storage _payable = payCompany.payables[receivable.payableId];

        receiveCompany.balance += receivable.amount;
        payCompany.balance -= receivable.amount;
        payCompany.credit += receivable.amount;

        _payable.amount -= receivable.amount;
        receivable.amount -= receivable.amount;

        // 如果应付款项结清，删除
        if (_payable.amount <= 0)
            delete payCompany.payables[receivable.payableId];

        // 如果应收款项结清，删除
        if (receivable.amount <= 0)
            delete receiveCompany.receivables[receivableId];

        emit Received(receivable.payer, receiver, receivable.amount, receivable.payableId, receivableId);
    }
}
